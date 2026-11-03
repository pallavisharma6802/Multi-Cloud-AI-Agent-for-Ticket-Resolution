#!/usr/bin/env python3
"""Build the vscode_support knowledge base from the REAL, official
microsoft/vscode-docs repository (CC-BY-3.0-US licensed) -- no Kaggle, no
synthetic data.

Source: https://github.com/microsoft/vscode-docs
Pulls:  docs/**/*.md, api/**/*.md, release-notes/*.md,
        remote-release-notes/*.md, learn/**/*.md

Each source markdown page is split on its H2 (`## `) headings into individual
retrievable KB documents (standard RAG chunking), written in the existing
domain-pack schema: {id, title, category, intent, content}.

Usage:
    git clone --depth 1 https://github.com/microsoft/vscode-docs <SRC>
    python data/prepare_vscode_docs.py --src <SRC> --out domains/vscode_support/kb
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

MIN_CHUNK_CHARS = 150

# top-level source folder -> KB category. Anything not listed falls into OTHER.
CATEGORY_MAP = {
    "setup": "INSTALLATION",
    "configure": "SETTINGS",
    "customization": "SETTINGS",
    "extension-docs": "EXTENSIONS",
    "terminal": "TERMINAL",
    "sourcecontrol": "GIT",
    "debugtest": "DEBUGGING",
    "editor": "EDITOR",
    "editing": "EDITOR",
    "languages": "LANGUAGES",
    "python": "LANGUAGES",
    "java": "LANGUAGES",
    "csharp": "LANGUAGES",
    "cpp": "LANGUAGES",
    "nodejs": "LANGUAGES",
    "typescript": "LANGUAGES",
    "datascience": "LANGUAGES",
    "azure": "REMOTE_CLOUD",
    "containers": "REMOTE_CLOUD",
    "devcontainers": "REMOTE_CLOUD",
    "remote": "REMOTE_CLOUD",
    "chat": "AI_FEATURES",
    "agents": "AI_FEATURES",
    "agent-customization": "AI_FEATURES",
    "intelligentapps": "AI_FEATURES",
    "getstarted": "GETTING_STARTED",
    "introvideos": "GETTING_STARTED",
    "enterprise": "ENTERPRISE",
    "reference": "REFERENCE",
    "supporting": "REFERENCE",
    "other": "REFERENCE",
    "api": "API_REFERENCE",
    "release-notes": "RELEASE_NOTES",
    "remote-release-notes": "RELEASE_NOTES",
    "learn": "GETTING_STARTED",
}

FRONT_MATTER_RE = re.compile(r"^---\n.*?\n---\n", re.S)
H2_RE = re.compile(r"^##\s+(.+)$", re.M)


def slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s.strip().lower()).strip("_")
    return s[:80] or "section"


def strip_front_matter(text: str) -> tuple[str, str]:
    """Return (title_from_front_matter_or_empty, body)."""
    m = FRONT_MATTER_RE.match(text)
    if not m:
        return "", text
    fm = m.group(0)
    title_m = re.search(r"^title:\s*(.+)$", fm, re.M | re.I)
    title = title_m.group(1).strip().strip('"\'') if title_m else ""
    return title, text[m.end():]


def chunk_markdown(body: str) -> list[tuple[str, str]]:
    """Split a markdown body on H2 headings. Returns [(heading, content), ...].
    If there are no H2s, the whole body is one chunk under heading ''."""
    matches = list(H2_RE.finditer(body))
    if not matches:
        return [("", body)]
    chunks = []
    # anything before the first H2 (intro paragraph) becomes its own chunk
    intro = body[: matches[0].start()].strip()
    if len(intro) >= MIN_CHUNK_CHARS:
        chunks.append(("", intro))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        chunks.append((m.group(1).strip(), body[start:end].strip()))
    return chunks


def category_for(rel_path: Path) -> str:
    parts = rel_path.parts
    # docs/<topic>/... -> key on <topic>; everything else keys on its own top folder
    top = parts[1] if parts[0] == "docs" and len(parts) > 1 else parts[0]
    return CATEGORY_MAP.get(top, "REFERENCE")


def build(src: Path, out: Path, globs: list[str], commit: str) -> list[dict]:
    docs: list[dict] = []
    seen_ids: set[str] = set()
    for pattern in globs:
        for path in sorted(src.glob(pattern)):
            if path.suffix != ".md":
                continue
            rel = path.relative_to(src)
            raw = path.read_text(encoding="utf-8", errors="ignore")
            fm_title, body = strip_front_matter(raw)
            page_title = fm_title or rel.stem.replace("-", " ")
            category = category_for(rel)
            page_slug = slugify(str(rel.with_suffix("")))
            for heading, content in chunk_markdown(body):
                content = content.strip()
                if len(content) < MIN_CHUNK_CHARS:
                    continue
                section_slug = slugify(heading) if heading else "overview"
                doc_id = f"{page_slug}__{section_slug}"
                n = 2
                base_id = doc_id
                while doc_id in seen_ids:
                    doc_id = f"{base_id}_{n}"
                    n += 1
                seen_ids.add(doc_id)
                title = f"{page_title} / {heading}" if heading else page_title
                source_url = (
                    f"https://github.com/microsoft/vscode-docs/blob/{commit}/{rel.as_posix()}"
                )
                docs.append({
                    "id": doc_id,
                    "title": title,
                    "category": category,
                    "intent": category.lower(),
                    "content": content,
                    "source": source_url,
                })
    return docs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="path to a clone of microsoft/vscode-docs")
    ap.add_argument("--out", required=True, help="output dir for KB json files")
    ap.add_argument("--min-docs", type=int, default=2000)
    args = ap.parse_args()

    src = Path(args.src)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for existing in out.glob("*.json"):
        existing.unlink()

    try:
        commit = subprocess.check_output(
            ["git", "-C", str(src), "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        commit = "unknown"

    globs = ["docs/**/*.md", "api/**/*.md", "release-notes/*.md",
             "remote-release-notes/*.md", "learn/**/*.md"]
    docs = build(src, out, globs, commit)

    for d in docs:
        (out / f"{d['id']}.json").write_text(json.dumps(d, indent=2), encoding="utf-8")

    print(f"wrote {len(docs)} KB documents to {out} (source commit {commit})")
    if len(docs) < args.min_docs:
        raise SystemExit(f"only {len(docs)} docs produced, wanted >= {args.min_docs}")

    by_cat: dict[str, int] = {}
    for d in docs:
        by_cat[d["category"]] = by_cat.get(d["category"], 0) + 1
    for cat, n in sorted(by_cat.items(), key=lambda kv: -kv[1]):
        print(f"  {cat:<16} {n}")
    print(f"source commit: {commit}")


if __name__ == "__main__":
    main()
