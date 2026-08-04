"""Drafts the customer-facing support response.

Confidence comes from JudgeAgent. On Reflexion retry, previous draft and
judge feedback are included so the model can correct specific issues.
"""
import logging
from typing import List, Optional

from app.config import settings
from app.llm.bedrock_client import LLMCallMetadata, get_llm_client
from app.schemas.response import KBDocument

logger = logging.getLogger(__name__)


class DraftingAgent:

    def __init__(self):
        self.client = get_llm_client()

    def draft_response(
        self,
        ticket_title: str,
        ticket_description: str,
        intent: str,
        kb_documents: List[KBDocument],
        previous_draft: Optional[str] = None,
        judge_feedback: Optional[str] = None,
    ) -> tuple[str, LLMCallMetadata]:
        logger.info(f"Drafting response for intent: {intent}")

        prompt = self._build_prompt(
            ticket_title=ticket_title,
            ticket_description=ticket_description,
            intent=intent,
            kb_documents=kb_documents,
            previous_draft=previous_draft,
            judge_feedback=judge_feedback,
        )

        from app.llm.model_router import resolve_model_for_role

        model = resolve_model_for_role("drafting")
        response_text, meta = self.client.generate_text(
            prompt=prompt,
            model=model,
            role="drafting",
            temperature=0.6,
            num_predict=500,
            timeout=settings.request_timeout_seconds,
        )
        logger.info(f"Response drafted ({len(response_text.split())} words)")
        return response_text, meta

    def _build_prompt(
        self,
        ticket_title: str,
        ticket_description: str,
        intent: str,
        kb_documents: List[KBDocument],
        previous_draft: Optional[str],
        judge_feedback: Optional[str],
    ) -> str:
        if kb_documents:
            context = "Relevant knowledge base articles (grader-approved as relevant to this ticket):\n\n"
            for i, doc in enumerate(kb_documents, 1):
                context += f"[Article {i}]\n{doc.content}\n\n"
        else:
            context = (
                "No knowledge base articles were found relevant to this issue. Acknowledge this honestly "
                "rather than inventing a solution.\n\n"
            )

        reflexion_block = ""
        if previous_draft and judge_feedback:
            reflexion_block = f"""
Your previous attempt at this response was reviewed and needs correction:

Previous draft:
{previous_draft}

Reviewer feedback:
{judge_feedback}

Write a corrected response that specifically fixes the issues above -- do not repeat unsupported claims.
"""

        return f"""You are a customer support agent helping resolve a support ticket.

Ticket Title: {ticket_title}
Ticket Description: {ticket_description}
Classified Intent: {intent}

{context}
{reflexion_block}
Instructions:
- Provide a clear, helpful response to the user's issue
- Base your answer ONLY on the knowledge base articles provided -- do not invent steps, policies, or facts not present in them
- Be professional, empathetic, and concise
- If the knowledge base doesn't have sufficient information, acknowledge this honestly and suggest the customer be connected with a human agent
- Keep the response under 300 words

Response:"""
