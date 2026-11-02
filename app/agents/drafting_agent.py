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
- Base self-service guidance ONLY on the provided articles. Do not invent steps, policies, URLs, phone numbers, email addresses, or account-specific facts.
- These articles are generic examples, not proof of this company's actual settings. Template variables such as {{{{Order Number}}}}, {{{{Website URL}}}}, and [Your Name] are missing information. Never copy unresolved template variables into the response, and never fill them with guessed values. Omit an unavailable detail or explain that a support specialist must supply it.
- No action tools have been invoked. You cannot look up a live order, issue a refund, create or modify an account, reset a password, cancel an order, or actually connect the customer to another agent. Never claim an action was performed, a transfer was completed, or a result was verified. Offer evidence-backed self-service instructions; otherwise explain that human follow-up is needed without pretending it has happened.
- A request for additional information is a clarification, not a resolution. If facts needed to resolve the issue are missing, state what remains unknown. Ask only for necessary non-sensitive information; never request passwords, access tokens, or full payment credentials.
- Respect an explicit request for a human. Acknowledge the request and say that the issue requires human follow-up instead of declaring it resolved.
- Be professional, empathetic, and concise. Normal courtesy does not need to be copied from an article. Avoid placeholder greetings or signatures.
- If the knowledge base lacks reliable actionable instructions, acknowledge that limit and recommend human review rather than inventing a solution.
- Keep the response under 300 words

Response:"""
