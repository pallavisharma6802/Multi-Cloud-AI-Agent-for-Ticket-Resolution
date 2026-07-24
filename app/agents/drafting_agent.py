"""Drafts the customer-facing support response.

Confidence comes from JudgeAgent. On Reflexion retry, previous draft and
judge feedback are included so the model can correct specific issues.
"""
import logging
from typing import List, Optional

from app.config import settings
from app.llm.ollama_client import LLMCallMetadata, get_llm_client
from app.schemas.response import KBDocument

logger = logging.getLogger(__name__)


class DraftingAgent:

    def __init__(self):
        self.client = get_llm_client()
        self.ollama_url = f"{settings.ollama_base_url}/api/generate"

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

        import requests

        try:
            payload = {
                "model": settings.model_drafting,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 500, "temperature": 0.6, "top_p": 0.9},
            }
            import time
            start = time.monotonic()
            response = requests.post(self.ollama_url, json=payload, timeout=settings.request_timeout_seconds)
            response.raise_for_status()
            result = response.json()
            response_text = result.get("response", "").strip()
            latency_ms = (time.monotonic() - start) * 1000

            meta = LLMCallMetadata(
                model=settings.model_drafting,
                role="drafting",
                latency_ms=round(latency_ms, 1),
                prompt_tokens=result.get("prompt_eval_count", 0),
                completion_tokens=result.get("eval_count", 0),
                attempts=1,
                raw_response_truncated=response_text[:300],
            )
            logger.info(f"Response drafted ({len(response_text.split())} words)")
            return response_text, meta

        except requests.exceptions.Timeout as e:
            logger.error("Ollama request timed out")
            raise RuntimeError("LLM request timed out") from e
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama request failed: {e}")
            raise RuntimeError(f"Failed to connect to LLM: {e}") from e

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
