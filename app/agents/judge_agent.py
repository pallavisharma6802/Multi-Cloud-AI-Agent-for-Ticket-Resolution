"""Self-RAG critic for drafted responses.

Scores faithfulness and relevance against graded-relevant documents.
Unsupported claims feed the Reflexion re-draft loop.
"""
from __future__ import annotations

import logging
from typing import List

from pydantic import BaseModel, Field

from app.config import settings
from app.llm.bedrock_client import LLMCallMetadata, get_llm_client
from app.schemas.response import KBDocument

logger = logging.getLogger(__name__)


class JudgeResult(BaseModel):
    faithfulness_score: float = Field(
        ge=0.0, le=1.0,
        description="How well every factual claim in the response is grounded in the provided documents "
        "(1.0 = fully grounded, 0.0 = entirely unsupported/hallucinated)",
    )
    relevance_score: float = Field(
        ge=0.0, le=1.0,
        description="How directly the response addresses the customer's actual question/issue",
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Overall confidence that this response is ready to send to the customer"
    )
    unsupported_claims: List[str] = Field(
        default_factory=list, description="Specific claims in the response not backed by any provided document"
    )
    rationale: str = Field(description="Brief explanation of the scores")


class JudgeAgent:
    def __init__(self):
        self.client = get_llm_client()

    def judge(
        self,
        ticket_text: str,
        response_text: str,
        relevant_documents: List[KBDocument],
    ) -> tuple[JudgeResult, LLMCallMetadata]:
        if relevant_documents:
            docs_block = "\n\n".join(
                f"[Doc {i+1}] {d.content}" for i, d in enumerate(relevant_documents)
            )
        else:
            docs_block = "(no documents were graded relevant -- any factual claim in the response is unsupported)"

        prompt = f"""You are a strict quality critic (Self-RAG style) reviewing a drafted customer-support response \
before it is sent.

Customer ticket:
{ticket_text}

Documents the response was allowed to draw on (only these count as "grounded"):
{docs_block}

Drafted response to evaluate:
{response_text}

Evaluate step by step:
1. List every factual/actionable claim the response makes.
2. For each claim, check whether it is actually supported by one of the documents above. If there are no \
documents, no factual claim can be grounded -- score faithfulness accordingly.
3. Judge whether the response actually addresses what the customer asked.
4. Give an overall confidence that this response is ready to send as-is, with no more revision.

Be strict: a well-written but ungrounded answer should score low on faithfulness even if it sounds confident."""

        result, meta = self.client.generate_structured(
            prompt=prompt,
            schema=JudgeResult,
            model=settings.model_judge,
            role="judge",
            temperature=0.0,
            num_predict=400,
        )
        return result, meta
