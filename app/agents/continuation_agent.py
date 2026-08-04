"""Continuation Agent: post-grading and post-judging next-step decisions.

Reasons over grading/judge history, priority, and cost so far. Hard caps in
supervisor.py force termination separately and are logged as anomalies.
"""
from __future__ import annotations

import logging
from typing import List, Literal

from pydantic import BaseModel, Field

from app.config import settings
from app.llm.bedrock_client import LLMCallMetadata, get_llm_client

logger = logging.getLogger(__name__)


class PostGradingDecision(BaseModel):
    action: Literal["rewrite_query", "proceed", "escalate"] = Field(
        description="rewrite_query: retry retrieval with a better query. "
        "proceed: draft a response from whatever relevant documents exist (even zero). "
        "escalate: give up on retrieval and send straight to a human."
    )
    rationale: str = Field(description="Why this action, given the priority and history so far")


class PostJudgingDecision(BaseModel):
    action: Literal["retry", "accept", "escalate"] = Field(
        description="retry: redraft the response incorporating the judge's feedback. "
        "accept: the response is good enough to send. "
        "escalate: stop trying and send to a human instead."
    )
    rationale: str = Field(description="Why this action, given the priority and history so far")


class ContinuationAgent:
    def __init__(self):
        self.client = get_llm_client()

    def decide_post_grading(
        self,
        ticket_text: str,
        priority: str,
        num_relevant: int,
        num_candidates: int,
        grading_rationales: List[str],
        iteration_count: int,
        llm_calls_so_far: int,
    ) -> tuple[PostGradingDecision, LLMCallMetadata]:
        rationale_block = "\n".join(f"- {r}" for r in grading_rationales) or "(none)"

        prompt = f"""You are the Continuation Agent deciding what to do next in a support-ticket resolution pipeline, \
right after document retrieval and grading.

Ticket priority: {priority}
Ticket: {ticket_text}

Retrieval result: {num_relevant} of {num_candidates} candidate documents were graded relevant.
Grading rationale for each candidate:
{rationale_block}

Progress so far: this is retrieval attempt #{iteration_count + 1}. {llm_calls_so_far} LLM calls have been made \
on this ticket so far.

Decide the next action:
- If retrieval clearly missed (few/no relevant docs) AND another attempt with a reformulated query is likely to \
help AND the ticket doesn't already have excessive attempts behind it, choose rewrite_query.
- If there are enough relevant documents to attempt a grounded answer (this can include zero documents for a \
question that doesn't actually need KB grounding, e.g. a simple acknowledgment), choose proceed.
- If retrieval has already been retried and still isn't finding anything relevant, or the ticket clearly needs \
a human regardless of what's retrieved, choose escalate.

Weigh cost: an urgent ticket justifies more attempts before escalating; a low-priority ticket that already failed \
once should not be retried indefinitely -- prefer proceeding with best-effort or escalating over spending more calls."""

        result, meta = self.client.generate_structured(
            prompt=prompt,
            schema=PostGradingDecision,
            model=settings.model_continuation,
            role="continuation_post_grading",
            temperature=0.1,
            num_predict=200,
        )
        return result, meta

    def decide_post_judging(
        self,
        ticket_text: str,
        priority: str,
        faithfulness_score: float,
        relevance_score: float,
        judge_confidence: float,
        unsupported_claims: List[str],
        judge_score_history: List[dict],
        iteration_count: int,
        llm_calls_so_far: int,
    ) -> tuple[PostJudgingDecision, LLMCallMetadata]:
        history_block = "\n".join(
            f"- attempt {i+1}: faithfulness={h['faithfulness_score']:.2f}, "
            f"relevance={h['relevance_score']:.2f}, confidence={h['confidence']:.2f}"
            for i, h in enumerate(judge_score_history)
        ) or "(this is the first attempt)"
        claims_block = "\n".join(f"- {c}" for c in unsupported_claims) or "(none flagged)"

        prompt = f"""You are the Continuation Agent deciding what to do next in a support-ticket resolution pipeline, \
right after a drafted response was judged.

Ticket priority: {priority}
Ticket: {ticket_text}

Judge's assessment of the current draft:
- Faithfulness (grounded in real documents, not hallucinated): {faithfulness_score:.2f}
- Relevance (actually answers the question): {relevance_score:.2f}
- Judge's own confidence this is ready to send: {judge_confidence:.2f}
- Unsupported claims flagged: {claims_block}

History of previous drafting attempts on this ticket:
{history_block}

Progress so far: this is drafting attempt #{iteration_count + 1}. {llm_calls_so_far} LLM calls have been made \
on this ticket so far.

Decide the next action:
- If the response has meaningful unsupported claims or is clearly not addressing the question, AND scores are \
trending upward or this is an early attempt, choose retry (the redraft will be given the judge's feedback).
- If the response is well-grounded and relevant, choose accept.
- If multiple retries haven't improved the scores, or an urgent/sensitive ticket has any faithfulness risk left, \
choose escalate rather than sending a possibly-wrong answer or looping indefinitely.

Weigh cost: don't recommend retry indefinitely if scores aren't improving across attempts."""

        result, meta = self.client.generate_structured(
            prompt=prompt,
            schema=PostJudgingDecision,
            model=settings.model_continuation,
            role="continuation_post_judging",
            temperature=0.1,
            num_predict=200,
        )
        return result, meta
