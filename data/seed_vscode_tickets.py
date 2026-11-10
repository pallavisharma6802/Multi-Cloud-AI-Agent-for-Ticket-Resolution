#!/usr/bin/env python3
"""Seed real VS Code support tickets through the live agent pipeline
(POST /api/v1/tickets) so the inbox/analytics have real, varied volume.

Usage: python data/seed_vscode_tickets.py [--base-url http://localhost:8000] [--n 20]
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

TICKETS = [
    ("Can't install VS Code on an M1 Mac", "I downloaded the macOS build but it says 'app is damaged and can't be opened'. How do I install it on Apple Silicon?"),
    ("Settings sync not working across devices", "I enabled Settings Sync but my keybindings and extensions aren't showing up on my second laptop. What am I missing?"),
    ("Extension marketplace won't load", "The Extensions view just spins forever and never lists anything, even for popular extensions. Is the marketplace down or is this a proxy issue?"),
    ("Integrated terminal opens to the wrong shell", "Every new terminal opens PowerShell but I want it to default to WSL bash. How do I change the default profile?"),
    ("Git graph shows no commits after pull", "After pulling from origin, Source Control shows no changes and the commit graph is empty even though 'git log' in a real terminal shows commits.", ),
    ("Debugger won't stop at breakpoints in Python", "I set breakpoints in a Flask app but the debugger runs straight through them. launch.json uses the debugpy adapter.", ),
    ("TypeScript IntelliSense extremely slow", "Autocomplete takes 5-10 seconds in a large monorepo. Is there a way to scope the TS server to a single workspace folder?", ),
    ("Remote-SSH connection keeps dropping", "Remote-SSH disconnects every few minutes with 'Could not establish connection'. Works fine with a plain ssh client.", ),
    ("Dev Container build fails on first open", "Reopening in container fails during the postCreateCommand step with a permissions error on /workspace.", ),
    ("Copilot Chat not citing any files", "When I ask Copilot Chat about my codebase it answers generically and never references actual files in my repo.", ),
    ("Can't find 'Open in Integrated Terminal' option", "Right-clicking a folder in Explorer no longer shows the Open in Integrated Terminal entry. It worked last week.", ),
    ("Workspace trust dialog loops forever", "Every time I open a folder it asks about workspace trust again, even after clicking 'Trust'.", ),
    ("Java extension pack fails to download language server", "The Java extension shows 'Downloading Java Linker' forever and never finishes on a locked-down network.", ),
    ("How do I format on save only for Python files", "I want format-on-save enabled only for .py files using black, not globally for every language.", ),
    ("Multi-root workspace loses terminal history", "Switching between folders in a multi-root workspace resets my terminal scrollback. Expected behavior?", ),
]


def submit_one(args_base_url, i, title, desc, total):
    try:
        r = requests.post(
            f"{args_base_url}/api/v1/tickets",
            json={
                "title": title,
                "description": desc,
                "user_email": f"seed-user-{i}@example.com",
                "domain_pack": "vscode_support",
            },
            timeout=180,
        )
        if r.status_code in (200, 201):
            body = r.json()
            print(f"[{i+1}/{total}] OK {body['ticket_id']} "
                  f"conf={body['confidence_score']:.2f} review={body['requires_human_review']}")
            return True
        print(f"[{i+1}] FAIL {r.status_code}: {r.text[:200]}")
        return False
    except Exception as e:
        print(f"[{i+1}] ERROR {e}")
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--n", type=int, default=len(TICKETS))
    ap.add_argument("--concurrency", type=int, default=2)
    args = ap.parse_args()

    subset = TICKETS[: args.n]
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [
            pool.submit(submit_one, args.base_url, i, title, desc, len(subset))
            for i, (title, desc) in enumerate(subset)
        ]
        for f in as_completed(futures):
            if f.result():
                ok += 1
            else:
                fail += 1
    print(f"\ndone: {ok} ok, {fail} failed")
    sys.exit(0 if fail == 0 else 1)


if __name__ == "__main__":
    main()
