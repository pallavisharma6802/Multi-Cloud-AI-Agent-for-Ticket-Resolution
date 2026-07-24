#!/usr/bin/env python3
"""Prepare the `it_saas` domain pack from Bitext customer-support data.

Source: https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset

Samples via the HF datasets-server `/rows` API (strided across offsets so all
intents appear). Labels are copied from the source; priority is advisory prose
only. Writes config, few-shots, KB articles, and eval/datasets/it_saas_test.jsonl.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from collections import defaultdict

import requests
import yaml

DATASET = "bitext/Bitext-customer-support-llm-chatbot-training-dataset"
DATASET_URL = f"https://huggingface.co/datasets/{DATASET}"
ROWS_API = "https://datasets-server.huggingface.co/rows"
SIZE_API = "https://datasets-server.huggingface.co/size"
PAGE_LEN = 100
SEED = 42

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PACK_DIR = os.path.join(REPO_ROOT, "domains", "it_saas")
OUT_KB_DIR = os.path.join(OUT_PACK_DIR, "kb")
OUT_EVAL_DIR = os.path.join(REPO_ROOT, "eval", "datasets")


def fetch_total_rows() -> int:
    resp = requests.get(SIZE_API, params={"dataset": DATASET}, timeout=30)
    resp.raise_for_status()
    return resp.json()["size"]["dataset"]["num_rows"]


def fetch_page(offset: int) -> list[dict]:
    for attempt in range(3):
        try:
            resp = requests.get(
                ROWS_API,
                params={
                    "dataset": DATASET,
                    "config": "default",
                    "split": "train",
                    "offset": offset,
                    "length": PAGE_LEN,
                },
                timeout=30,
            )
            resp.raise_for_status()
            return [r["row"] for r in resp.json()["rows"]]
        except requests.exceptions.RequestException as e:
            if attempt == 2:
                raise
            print(f"  retry offset={offset} after error: {e}", file=sys.stderr)
            time.sleep(2)
    return []


def fetch_strided_sample(total_rows: int, stride: int) -> list[dict]:
    rows: list[dict] = []
    offsets = list(range(0, total_rows, stride))
    print(f"Fetching {len(offsets)} pages of {PAGE_LEN} rows (stride={stride}) "
          f"from {total_rows} total real rows...")
    for i, offset in enumerate(offsets):
        page = fetch_page(offset)
        rows.extend(page)
        if (i + 1) % 10 == 0 or i == len(offsets) - 1:
            print(f"  fetched {i + 1}/{len(offsets)} pages ({len(rows)} rows so far)")
    return rows


def build_description(intent: str, category: str) -> str:
    human_intent = intent.replace("_", " ")
    return f"Customer inquiries about {human_intent} (category: {category})."


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stride", type=int, default=800,
                         help="Offset stride between sampled pages of 100 rows")
    parser.add_argument("--test-size", type=int, default=900,
                         help="Number of held-out rows for the eval test set")
    parser.add_argument("--kb-per-intent", type=int, default=4,
                         help="Distinct real responses to keep as KB articles per intent")
    parser.add_argument("--fewshot-per-intent", type=int, default=3)
    args = parser.parse_args()

    random.seed(SEED)

    total_rows = fetch_total_rows()
    rows = fetch_strided_sample(total_rows, args.stride)
    print(f"Sampled {len(rows)} real rows spread across the full dataset.")

    by_intent = defaultdict(list)
    for r in rows:
        by_intent[(r["category"], r["intent"])].append(r)

    print(f"Discovered {len(by_intent)} distinct (category, intent) pairs from real data.")

    random.shuffle(rows)
    n_test = min(args.test_size, len(rows) // 3)
    test_rows = rows[:n_test]
    pool_rows = rows[n_test:]

    pool_by_intent = defaultdict(list)
    for r in pool_rows:
        pool_by_intent[(r["category"], r["intent"])].append(r)

    os.makedirs(OUT_KB_DIR, exist_ok=True)
    os.makedirs(OUT_EVAL_DIR, exist_ok=True)

    intents = []
    few_shot_examples = []
    kb_categories = set()
    kb_count = 0

    for (category, intent), items in sorted(pool_by_intent.items()):
        kb_categories.add(category)
        intents.append({
            "id": intent,
            "category": category,
            "description": build_description(intent, category),
        })

        seen_responses = set()
        n_kb = 0
        for item in items:
            resp_text = item["response"].strip()
            if resp_text in seen_responses:
                continue
            seen_responses.add(resp_text)
            kb_doc = {
                "id": f"{intent}_{n_kb:02d}",
                "title": f"{intent.replace('_', ' ').title()} ({category})",
                "category": category,
                "intent": intent,
                "content": resp_text,
                "source": DATASET_URL,
            }
            with open(os.path.join(OUT_KB_DIR, f"{intent}_{n_kb:02d}.json"), "w") as f:
                json.dump(kb_doc, f, indent=2)
            n_kb += 1
            kb_count += 1
            if n_kb >= args.kb_per_intent:
                break

        for item in items[: args.fewshot_per_intent]:
            few_shot_examples.append({
                "text": item["instruction"].strip(),
                "intent": intent,
                "category": category,
                "priority_hint": None,
            })

    config = {
        "id": "it_saas",
        "display_name": "IT / SaaS Customer Support",
        "description": (
            "Generic SaaS/IT product support taxonomy sourced from the Bitext "
            "customer-support intent corpus: 27 real, human-authored intents "
            "across 10 categories (orders, accounts, billing, refunds, "
            "shipping, subscriptions, and general contact/feedback)."
        ),
        "source_dataset": {
            "name": DATASET,
            "url": DATASET_URL,
            "license": "cdla-sharing-1.0",
            "real_data": True,
            "num_source_rows": total_rows,
            "limitations": (
                f"Sampled {len(rows)} of {total_rows} real rows (strided across the "
                "full dataset for intent coverage) rather than the full corpus, "
                "for pipeline build speed. No priority labels exist in the source "
                "data -- priority_guidance below is advisory prose for the LLM, "
                "not a derived label."
            ),
        },
        "intents": intents,
        "priority_guidance": (
            "Reason about urgency from the customer's own words and the entities/"
            "sentiment already extracted, not from the intent category alone. "
            "Signals that typically indicate higher urgency: the customer states "
            "they cannot access something they are paying for right now (e.g. a "
            "blocked account, a failed payment blocking service, an active "
            "service outage), strongly negative sentiment combined with an "
            "explicit deadline or threat to cancel, or repeated contact about the "
            "same unresolved issue. Signals that typically indicate lower "
            "urgency: general how-to questions, feedback/suggestions, or "
            "requests that have no stated time pressure. Category alone (e.g. "
            "'REFUND') does not determine priority -- a calm, no-deadline refund "
            "question is not automatically high priority, and a calmly-worded "
            "account lockout during a paid trial can still be urgent."
        ),
        "kb_categories": sorted(kb_categories),
        "intent_eval_available": True,
    }

    with open(os.path.join(OUT_PACK_DIR, "config.yaml"), "w") as f:
        yaml.safe_dump(config, f, sort_keys=False, allow_unicode=True, width=100)

    with open(os.path.join(OUT_PACK_DIR, "few_shot_examples.json"), "w") as f:
        json.dump(few_shot_examples, f, indent=2)

    with open(os.path.join(OUT_EVAL_DIR, "it_saas_test.jsonl"), "w") as f:
        for r in test_rows:
            f.write(json.dumps({
                "text": r["instruction"].strip(),
                "true_intent": r["intent"],
                "true_category": r["category"],
            }) + "\n")

    print(f"\nWrote {len(intents)} intents, {kb_count} KB articles, "
          f"{len(few_shot_examples)} few-shot examples, "
          f"{len(test_rows)} held-out eval rows.")
    print(f"Pack: {OUT_PACK_DIR}")
    print(f"Eval test set: {os.path.join(OUT_EVAL_DIR, 'it_saas_test.jsonl')}")


if __name__ == "__main__":
    main()
