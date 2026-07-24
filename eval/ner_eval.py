"""Entity-level NER evaluation via seqeval.

Requires a CoNLL-format gold file (`--gold-file`). Neither Bitext nor NHS GP
reviews ships token-level entity labels, so without a gold file this reports
the metric as unavailable rather than scoring Azure against itself.
"""
from __future__ import annotations

import argparse
import json


def _read_conll(path: str) -> tuple[list[list[str]], list[list[str]]]:
    sentences_tokens: list[list[str]] = []
    sentences_tags: list[list[str]] = []
    tokens: list[str] = []
    tags: list[str] = []

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                if tokens:
                    sentences_tokens.append(tokens)
                    sentences_tags.append(tags)
                    tokens, tags = [], []
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            tokens.append(parts[0])
            tags.append(parts[-1])
    if tokens:
        sentences_tokens.append(tokens)
        sentences_tags.append(tags)
    return sentences_tokens, sentences_tags


def _azure_entities_to_bio(tokens: list[str], entities: list[dict]) -> list[str]:
    tags = ["O"] * len(tokens)
    entity_texts = {e["text"].lower() for e in entities}
    for i, tok in enumerate(tokens):
        if tok.lower() in entity_texts:
            tags[i] = "B-ENT" if (i == 0 or tags[i - 1] == "O") else "I-ENT"
    return tags


def evaluate_ner(gold_file: str | None) -> dict:
    if not gold_file:
        return {
            "metric": "ner_entity_f1",
            "available": False,
            "reason": "No CoNLL gold NER file provided. Pass --gold-file to compute this metric.",
        }

    from seqeval.metrics import classification_report as seq_report
    from seqeval.metrics import f1_score, precision_score, recall_score

    from app.agents.azure_nlp_agent import AzureNLPAgent

    tokens_list, gold_tags_list = _read_conll(gold_file)
    agent = AzureNLPAgent()

    pred_tags_list = []
    for tokens in tokens_list:
        text = " ".join(tokens)
        signals = agent.analyze_ticket(title="", description=text)
        pred_tags_list.append(_azure_entities_to_bio(tokens, signals.entities))

    return {
        "metric": "ner_entity_f1",
        "available": True,
        "num_sentences": len(tokens_list),
        "precision": round(precision_score(gold_tags_list, pred_tags_list), 4),
        "recall": round(recall_score(gold_tags_list, pred_tags_list), 4),
        "f1": round(f1_score(gold_tags_list, pred_tags_list), 4),
        "report": seq_report(gold_tags_list, pred_tags_list),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-file", default=None, help="CoNLL-format labeled NER test file (optional)")
    args = parser.parse_args()
    print(json.dumps(evaluate_ner(args.gold_file), indent=2))
