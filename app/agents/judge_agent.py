"""Self-RAG critic for drafted responses.

Scores faithfulness and relevance against graded-relevant documents.
Unsupported claims feed the Reflexion re-draft loop.
"""
from __future__ import annotations

import logging
import re
from typing import List

from pydantic import BaseModel, Field

from app.config import settings
from app.llm.bedrock_client import LLMCallMetadata, get_llm_client
from app.schemas.response import KBDocument

logger = logging.getLogger(__name__)

# The judge's own prompt (rule 5 below) tells it that an omission phrased as
# "the draft does not mention X" is not an unsupported claim, but
# amazon.nova-lite-v1:0 doesn't reliably follow that rule even given matching
# examples -- measured on a 109-ticket live batch, roughly 20 of the escalated
# tickets were flagged on exactly this omission pattern. Enforce the judge's
# own stated rule in code as a backstop rather than trusting compliance.
_OMISSION_RE = re.compile(
    r"does not (?:mention|state|explicitly|provide|specify)|"
    r"is not (?:mentioned|explicitly|stated)|"
    r"without (?:providing|explicitly|mentioning|stating)|"
    r"not explicitly (?:mentioned|stated|supported|state)",
    re.IGNORECASE,
)
# Also seen in production: the judge occasionally puts a plainly affirmative
# statement ("the URLs provided are accurate and necessary") or a non-claim
# fragment ("The WSL service is running.") into unsupported_claims, directly
# contradicting its own instruction never to do that. Require some actual
# negative/failure language before accepting an entry as a real claim.
_NEGATIVE_INDICATOR_RE = re.compile(
    r"\b(incorrect|inaccurate|wrong|invented|hallucinat|fabricat|false|untrue|"
    r"misleading|unsafe|not accurate|does not exist|no such|not true)\b",
    re.IGNORECASE,
)


def _is_valid_unsupported_claim(claim: str) -> bool:
    if _OMISSION_RE.search(claim):
        return False
    if "not" not in claim.lower() and not _NEGATIVE_INDICATOR_RE.search(claim):
        return False
    return True


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
        description="Quote the exact factual statement FROM THE DRAFT that is unsupported or unsafe. "
        "Do not list omitted details, reviewer suggestions, or statements that are not in the draft. "
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
                f"[Doc {i+1}] Source URL: {d.metadata.get('source', 'unavailable')}\n{d.content}" for i, d in enumerate(relevant_documents)
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

Scoring examples (apply the same principles, not these product facts):
- Evidence: "Open Settings and change Font Size. The default installation folder is X." Draft: "Open Settings and change Font Size." Verdict: faithfulness 1.0, relevance 1.0, unsupported_claims []. Not mentioning a folder is NOT a claim and does not matter to changing font size.
- Evidence: "Setup adds the application to PATH; restart your console." Draft: "Install it and restart your console." Verdict: grounded and usable; unsupported_claims []. Do not require the draft to state every implementation detail.
- Evidence names a menu command but represents its shortcut with a macro. Draft names the command without a shortcut. Verdict: grounded; do not demand a guessed keyboard shortcut.
- Evidence gives Windows instructions. Draft gives a macOS-only command. Verdict: flag the exact incorrect instruction; require correction.
- Draft promises a refund that no tool performed. Verdict: flag the exact promise; require human review.
- Draft gives correct steps but never says "make sure the relevant extension is installed first," even though that would be helpful context. Verdict: grounded; unsupported_claims []. An omitted-but-helpful prerequisite is not a false statement -- it is missing advice, not an unsupported claim, and must not be flagged even if a human reviewer would have added it.
- Evidence's source URL is given once in the document metadata. Draft says "see the official guide" without repeating that URL inline. Verdict: grounded; unsupported_claims []. Not restating an already-supplied URL is not an unsupported claim.

Evaluate material claims, not harmless writing style:
1. Check factual assertions, policy details, instructions, and promised or completed actions against the documents and facts explicitly supplied in the ticket. Generic politeness, empathy, ordinary greetings, and a courteous sign-off do not need documentary support. Do not lower faithfulness just because a phrase such as "thank you" or "happy to help" is absent from the articles.
2. The knowledge articles may contain unfilled templates. A literal {{{{Website URL}}}}, {{{{Order Number}}}}, [Your Name], or other unresolved variable is not usable customer guidance, even if copied faithfully from an article. Invented URLs or phone numbers and undefined template-based steps are material failures that require revision or human review. Do not require a URL, phone number, email address, or exact UI label that the evidence does not supply. Omitting unavailable contact details is not an unsupported claim. Accept a qualified self-service description such as "password reset option" when the evidence describes an equivalent option; do not force the draft to invent details or bracketed substitutes.
3. No action tools have been invoked. Any claim that the system has looked up an order, issued a refund, created or modified an account, reset a password, canceled an order, or transferred the customer to a person is unsupported. A template article that promises such an action does not prove it happened.
4. Check whether the response addresses the actual request. Asking for needed information is a clarification, not evidence that the issue was resolved. An explicit human request must remain a human follow-up. Honest limitations and a recommendation for review are appropriate when self-service evidence is insufficient.
5. In unsupported_claims, list ONLY actual material unsupported or unsafe statements from this draft and explain the missing support. Never include a claim while saying it IS grounded or supported. Use an empty list when there are no such failures. Do not invent an issue merely to populate the list. Before adding any item, verify that it identifies an actual assertion in the current draft. "The draft does not mention ..." is not an unsupported assertion. A minor optional omission must not reduce faithfulness, confidence, or trigger revision. If a necessary safety step is absent, describe it as a safety failure in the rationale, not as an invented claim. REJECT any candidate entry whose own wording is phrased as an absence -- "does not mention", "does not explicitly state", "is not explicitly mentioned", "without providing a specific", "without repeating the" -- those phrasings describe something missing from the draft, not something false in the draft, and must never appear in unsupported_claims regardless of how useful the missing detail would have been.
6. Source URLs supplied in document metadata are valid evidence for citations. Relative links resolved against that source URL are also grounded. A documentation macro is missing display information, not permission to invent a shortcut. An answer may use a documented command name without giving a keyboard shortcut. Do not flag an exact supplied source URL merely because it is not repeated in the article body. Distinguish an omitted optional detail from an unsupported assertion: a short answer need not reproduce the entire article. Flag omissions only if they make the requested steps materially unsafe or unusable. Never mix instructions for different operating systems.
7. Score faithfulness and relevance independently, then state whether this draft is ready to send as-is. Unresolved templates, invented contact details, and claims of unperformed actions must lower readiness confidence and be called out clearly. Do not demand repeated redrafts solely to remove harmless courtesy.

Be strict about material facts and capabilities. Fluent wording is not evidence of correctness."""

        result, meta = self.client.generate_structured(
            prompt=prompt,
            schema=JudgeResult,
            model=settings.model_judge,
            role="judge",
            temperature=0.0,
            num_predict=400,
        )

        filtered = [c for c in result.unsupported_claims if _is_valid_unsupported_claim(c)]
        if len(filtered) != len(result.unsupported_claims):
            dropped = [c for c in result.unsupported_claims if c not in filtered]
            logger.info(f"Judge: dropped {len(dropped)} non-compliant unsupported_claims entries: {dropped}")
            result = result.model_copy(update={"unsupported_claims": filtered})

        return result, meta
