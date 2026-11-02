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
        default_factory=list,
        description="Material factual or action claims that are actually unsupported or unsafe as written. "
        "Do not list grounded claims or harmless courtesy. Unfilled template values and claims of unperformed actions are failures.",
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
            docs_block = (
                "(no documents were graded relevant -- do not accept invented solution steps or policies; "
                "an honest acknowledgment, necessary clarification, or recommendation for human follow-up may still be appropriate)"
            )

        prompt = f"""You are a strict quality critic (Self-RAG style) reviewing a drafted customer-support response \
before it is sent.

Customer ticket:
{ticket_text}

Documents the response was allowed to draw on (only these count as "grounded"):
{docs_block}

Drafted response to evaluate:
{response_text}

Evaluate material claims, not harmless writing style:
1. Check factual assertions, policy details, instructions, and promised or completed actions against the documents and facts explicitly supplied in the ticket. Generic politeness, empathy, ordinary greetings, and a courteous sign-off do not need documentary support. Do not lower faithfulness just because a phrase such as "thank you" or "happy to help" is absent from the articles.
2. The knowledge articles may contain unfilled templates. A literal {{{{Website URL}}}}, {{{{Order Number}}}}, [Your Name], or other unresolved variable is not usable customer guidance, even if copied faithfully from an article. Missing contact details, invented URLs or phone numbers, and undefined template-based steps are material failures that require revision or human review.
3. No action tools have been invoked. Any claim that the system has looked up an order, issued a refund, created or modified an account, reset a password, canceled an order, or transferred the customer to a person is unsupported. A template article that promises such an action does not prove it happened.
4. Check whether the response addresses the actual request. Asking for needed information is a clarification, not evidence that the issue was resolved. An explicit human request must remain a human follow-up. Honest limitations and a recommendation for review are appropriate when self-service evidence is insufficient.
5. In unsupported_claims, list ONLY actual material unsupported or unsafe statements from this draft and explain the missing support. Never include a claim while saying it IS grounded or supported. Use an empty list when there are no such failures. Do not invent an issue merely to populate the list.
6. Score faithfulness and relevance independently, then state whether this draft is ready to send as-is. Unresolved templates, invented contact details, and claims of unperformed actions must lower readiness confidence and be called out clearly. Do not demand repeated redrafts solely to remove harmless courtesy.

Be strict about material facts and capabilities. Fluent wording is not evidence of correctness."""

        result, meta = self.client.generate_structured(
            prompt=prompt,
            schema=JudgeResult,
            model=settings.model_judge,
            role="judge",
            temperature=0.0,
            num_predict=400,
        )
        return result, meta
