"""RAG quality evaluation via ragas (reference-free metrics).

Needs a live Ollama server and a seeded KB (`python seed_kb.py --pack <id>`).
Reports faithfulness and answer_relevancy. context_precision / context_recall
need human reference answers and are left unavailable unless collected later.
Uses project Ollama + local sentence-transformers (no OpenAI key).
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
from app.config import settings

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
    try:
        from datasets import Dataset
        from langchain_community.embeddings import HuggingFaceEmbeddings
        from langchain_community.llms import Ollama as LangchainOllama
        from ragas import evaluate as ragas_evaluate
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import answer_relevancy, faithfulness
    except ImportError as e:
        return {"metric": "rag_quality", "available": False, "reason": f"ragas/langchain deps not installed: {e}"}

    data = build_rag_dataset(pack_id, max_examples)
    if not data["question"]:
        return {"metric": "rag_quality", "available": False, "reason": "no eval examples found"}

    dataset = Dataset.from_dict(data)

    judge_llm = LangchainLLMWrapper(LangchainOllama(base_url=settings.ollama_base_url, model=settings.model_judge))
    embeddings = LangchainEmbeddingsWrapper(HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2"))

    result = ragas_evaluate(
        dataset, metrics=[faithfulness, answer_relevancy], llm=judge_llm, embeddings=embeddings
    )
    scores = result.to_pandas()[["faithfulness", "answer_relevancy"]].mean().to_dict()

    return {
        "pack": pack_id,
        "metric": "rag_quality",
        "available": True,
        "num_examples": len(data["question"]),
        "faithfulness": round(float(scores.get("faithfulness", 0.0)), 4),
        "answer_relevancy": round(float(scores.get("answer_relevancy", 0.0)), 4),
        "context_precision": None,
        "context_recall": None,
        "context_metrics_note": (
            "context_precision/context_recall require reference answers; not computed "
            "(see module docstring)."
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", default="it_saas")
    parser.add_argument("--max-examples", type=int, default=30)
    args = parser.parse_args()
    print(json.dumps(evaluate_rag(args.pack, args.max_examples), indent=2))
