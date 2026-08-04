"""RAG quality evaluation via ragas (reference-free metrics).

Requires a seeded KB (`python seed_kb.py --pack <id>`) and a Bedrock-backed
judge once wired. Until then ``evaluate_rag`` reports ``available: false``
honestly — the LangchainOllama path was removed with the Ollama runtime.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.document_grader import DocumentGrader
from app.agents.drafting_agent import DraftingAgent
from app.agents.retrieval_agent import RetrievalAgent

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_samples(pack_id: str, max_examples: int):
    test_path = os.path.join(REPO_ROOT, "eval", "datasets", f"{pack_id}_test.jsonl")
    with open(test_path) as f:
        examples = [json.loads(line) for line in f]
    return examples[:max_examples]


def build_rag_dataset(pack_id: str, max_examples: int = 30) -> dict:
    """Run retrieve → grade → draft; return ragas-shaped {question, answer, contexts}."""
    retrieval_agent = RetrievalAgent(domain_pack_id=pack_id)
    grader = DocumentGrader()
    drafter = DraftingAgent()

    questions, answers, contexts_list = [], [], []
    for ex in _load_samples(pack_id, max_examples):
        question = ex["text"]
        candidates = retrieval_agent.retrieve_relevant_documents(question, top_k=5)
        graded, _ = grader.grade_documents(question, candidates)
        relevant_docs = [g.document for g in graded if g.relevant]

        answer, _ = drafter.draft_response(
            ticket_title="", ticket_description=question,
            intent=ex.get("true_intent") or "unknown", kb_documents=relevant_docs,
        )

        questions.append(question)
        answers.append(answer)
        contexts_list.append([d.content for d in relevant_docs] or ["(no relevant documents found)"])

    return {"question": questions, "answer": answers, "contexts": contexts_list}


def evaluate_rag(pack_id: str, max_examples: int = 30) -> dict:
    """Report RAG metrics unavailable until a Bedrock judge is wired into ragas."""
    _ = max_examples
    return {
        "pack": pack_id,
        "metric": "rag_quality",
        "available": False,
        "reason": (
            "RAGAS judge not yet wired to Amazon Bedrock (LangchainOllama removed). "
            "Use live smoke / intent eval against Bedrock instead; see README."
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", default="it_saas")
    parser.add_argument("--max-examples", type=int, default=30)
    args = parser.parse_args()
    print(json.dumps(evaluate_rag(args.pack, args.max_examples), indent=2))
