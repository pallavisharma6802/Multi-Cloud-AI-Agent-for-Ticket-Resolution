#!/usr/bin/env python3
"""Prepare the `healthcare` domain pack from NHS GP patient reviews.

Source: https://huggingface.co/datasets/janduplessis886/england-nhs-gp-reviews

No intent labels in the source. `intent_eval_available` stays false; star_rating
is kept as ground truth for priority/severity checks.

Writes config, few-shots, KB articles, and eval/datasets/healthcare_test.jsonl.
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

HF_DATASET = "janduplessis886/england-nhs-gp-reviews"
HF_ROWS_URL = f"https://datasets-server.huggingface.co/rows?dataset={HF_DATASET}&config=default&split=train"
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOMAIN_DIR = os.path.join(REPO_ROOT, "domains", "healthcare")
KB_DIR = os.path.join(DOMAIN_DIR, "kb")
EVAL_DIR = os.path.join(REPO_ROOT, "eval", "datasets")

# Hand-mapped illustrative few-shots only (not eval labels).
FEW_SHOT_INTENT_HINTS = {
    "appointment": "appointment_access",
    "waiting": "appointment_access",
    "phone": "appointment_access",
    "call back": "communication_issue",
    "rude": "staff_conduct",
    "prescription": "prescription_medication",
    "medication": "prescription_medication",
    "diagnosis": "clinical_concern",
    "misdiagnos": "clinical_concern",
    "referral": "administration_records",
    "records": "administration_records",
}

INTENTS = [
    {"id": "appointment_access", "category": "ACCESS",
     "description": "Difficulty getting/booking an appointment, long waits to be seen, or phone/reception access problems."},
    {"id": "clinical_concern", "category": "CLINICAL",
     "description": "Concerns about the quality, safety, or accuracy of clinical care, diagnosis, or test results."},
    {"id": "communication_issue", "category": "COMMUNICATION",
     "description": "Problems with how information was communicated (unclear explanations, not being kept informed, missed callbacks)."},
    {"id": "staff_conduct", "category": "STAFF",
     "description": "Feedback specifically about staff attitude, courtesy, or professionalism (positive or negative)."},
    {"id": "prescription_medication", "category": "PRESCRIBING",
     "description": "Issues with prescriptions, medication reviews, or pharmacy coordination."},
    {"id": "administration_records", "category": "ADMIN",
     "description": "Administrative issues: records, referrals, registration, billing/coding errors, digital portal problems."},
    {"id": "positive_feedback", "category": "FEEDBACK",
     "description": "Primarily positive praise for the practice, care, or staff (no actionable complaint)."},
]

PRIORITY_GUIDANCE = """\
Priority is advisory reasoning guidance for the LLM, not a rule table.
- urgent: clinical safety risk, severe untreated symptoms, vulnerable patient left without care
- high: long denied access to needed care, repeated failed contact, clear patient harm risk
- medium: significant frustration or delay without immediate safety risk
- low: minor admin friction, or primarily positive feedback
Star rating (1-5) from the patient is a useful severity signal but not a direct mapping.
"""


def fetch_rows(offset: int, length: int = 100, retries: int = 3) -> list[dict]:
    url = f"{HF_ROWS_URL}&offset={offset}&length={length}"
    for attempt in range(retries):
        r = requests.get(url, timeout=60)
        if r.status_code == 200:
            return [row["row"] for row in r.json().get("rows", [])]
        if r.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
    return []


def guess_intent_for_fewshot(text: str, star_rating: int) -> str:
    lower = text.lower()
    if star_rating >= 4 and not any(k in lower for k in ("rude", "wait", "appoint", "prescription")):
        return "positive_feedback"
    for needle, intent in FEW_SHOT_INTENT_HINTS.items():
        if needle in lower:
            return intent
    return "appointment_access" if star_rating <= 2 else "positive_feedback"


def write_config():
    os.makedirs(DOMAIN_DIR, exist_ok=True)
    config = {
        "id": "healthcare",
        "display_name": "Healthcare — Patient Feedback Triage (NHS GP)",
        "description": (
            "Patient feedback/complaint triage for GP practices, built from "
            "real patient reviews of NHS GP surgeries."
        ),
        "source_dataset": {
            "name": HF_DATASET,
            "url": f"https://huggingface.co/datasets/{HF_DATASET}",
            "license": "unknown-public-nhs-review-data",
            "real_data": True,
            "num_source_rows": 61955,
            "limitations": (
                "No per-row intent/category labels. Taxonomy is advisory "
                "(NHS England GP-complaint categories). intent_eval_available "
                "is false; star_rating is used for priority/severity correlation."
            ),
        },
        "intents": INTENTS,
        "priority_guidance": PRIORITY_GUIDANCE,
        "kb_categories": ["ACCESS", "CLINICAL", "COMMUNICATION", "STAFF", "PRESCRIBING", "ADMIN", "FEEDBACK"],
        "intent_eval_available": False,
    }
    with open(os.path.join(DOMAIN_DIR, "config.yaml"), "w") as f:
        yaml.safe_dump(config, f, sort_keys=False, width=100)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb-count", type=int, default=150)
    parser.add_argument("--eval-count", type=int, default=200)
    parser.add_argument("--few-shot-count", type=int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    random.seed(args.seed)

    write_config()
    os.makedirs(KB_DIR, exist_ok=True)
    os.makedirs(EVAL_DIR, exist_ok=True)

    # Stride across the dataset so we are not stuck in one rating band.
    total_needed = args.kb_count + args.eval_count + args.few_shot_count + 50
    stride = max(1, 61955 // (total_needed // 50 + 1))
    collected: list[dict] = []
    offset = 0
    while len(collected) < total_needed and offset < 61955:
        batch = fetch_rows(offset, length=100)
        if not batch:
            break
        for row in batch:
            comment = (row.get("comment") or "").strip()
            if len(comment) < 40:
                continue
            collected.append({
                "title": (row.get("title") or "").strip(),
                "comment": comment,
                "star_rating": int(row.get("star_rating") or 0),
                "surgeryname": row.get("surgeryname") or "",
            })
        offset += stride
        time.sleep(0.15)

    if len(collected) < 50:
        print(f"Only fetched {len(collected)} usable rows; aborting.", file=sys.stderr)
        sys.exit(1)

    random.shuffle(collected)

    # KB from positive reviews (what good practice looks like).
    positives = [r for r in collected if r["star_rating"] >= 4]
    kb_rows = positives[: args.kb_count]
    for i, row in enumerate(kb_rows):
        doc = {
            "id": f"nhs_review_{i:03d}",
            "content": row["comment"],
            "source": f"https://huggingface.co/datasets/{HF_DATASET}",
            "category": "FEEDBACK",
            "intent": "positive_feedback",
            "metadata": {"star_rating": row["star_rating"], "surgery": row["surgeryname"]},
        }
        with open(os.path.join(KB_DIR, f"{doc['id']}.json"), "w") as f:
            json.dump(doc, f, indent=2)

    remaining = [r for r in collected if r not in kb_rows]

    # Few-shots: illustrative only.
    few_shots = []
    for row in remaining[: args.few_shot_count]:
        text = row["comment"][:400]
        few_shots.append({
            "text": text,
            "intent": guess_intent_for_fewshot(text, row["star_rating"]),
            "note": "illustrative hand-mapped few-shot; not eval ground truth",
        })
    with open(os.path.join(DOMAIN_DIR, "few_shot_examples.json"), "w") as f:
        json.dump(few_shots, f, indent=2)

    # Held-out eval: real text + star_rating; intent left null.
    test_rows = []
    for row in remaining[args.few_shot_count: args.few_shot_count + args.eval_count]:
        test_rows.append({
            "text": row["comment"],
            "true_intent": None,
            "true_category": None,
            "real_star_rating": row["star_rating"],
        })
    eval_path = os.path.join(EVAL_DIR, "healthcare_test.jsonl")
    with open(eval_path, "w") as f:
        for row in test_rows:
            f.write(json.dumps(row) + "\n")

    print(
        f"Wrote {len(kb_rows)} KB docs, {len(few_shots)} few-shots, "
        f"{len(test_rows)} eval rows to {DOMAIN_DIR} / {eval_path}"
    )


if __name__ == "__main__":
    main()
