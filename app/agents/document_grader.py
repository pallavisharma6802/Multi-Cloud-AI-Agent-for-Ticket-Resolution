"""CRAG document grader: LLM relevance checks and query rewrite.

Grades each retrieval candidate by content, then can rewrite the query when
too few documents are relevant.
"""
from __future__ import annotations

import logging
from typing import List

from pydantic import BaseModel, Field

from app.config import settings
from app.llm.ollama_client import LLMCallMetadata, get_llm_client
from app.schemas.response import KBDocument

logger = logging.getLogger(__name__)


class RelevanceGrade(BaseModel):
    relevant: bool = Field(description="Whether this document's content actually helps resolve the ticket")
    rationale: str = Field(description="One sentence explaining why")


class GradedDocument(BaseModel):
    document: KBDocument
    relevant: bool
    rationale: str


class RewrittenQuery(BaseModel):
    rewritten_query: str = Field(description="A reformulated search query more likely to retrieve relevant documents")
    rationale: str = Field(description="Why this reformulation should retrieve better results")


class DocumentGrader:
    def __init__(self):
        self.client = get_llm_client()

    def grade_documents(
        self, ticket_text: str, documents: List[KBDocument]
    ) -> tuple[List[GradedDocument], List[LLMCallMetadata]]:
        graded: List[GradedDocument] = []
        metadatas: List[LLMCallMetadata] = []

        for doc in documents:
            prompt = f"""You are a relevance grader for a support-ticket retrieval system.

Ticket:
{ticket_text}

Candidate knowledge-base document:
{doc.content}

Does this document contain information that would actually help resolve the ticket above? \
Judge based on substantive content overlap, not superficial keyword overlap. \
A document about a related-but-different topic should be marked not relevant."""

            try:
                grade, meta = self.client.generate_structured(
                    prompt=prompt,
                    schema=RelevanceGrade,
                    model=settings.model_grader,
                    role="document_grader",
                    temperature=0.0,
                    num_predict=150,
                )
                graded.append(GradedDocument(document=doc, relevant=grade.relevant, rationale=grade.rationale))
                metadatas.append(meta)
            except RuntimeError as e:
                logger.error(f"document_grader failed for doc {doc.doc_id}: {e}")
                # Fail closed: treat ungraded docs as not relevant.
                graded.append(GradedDocument(
                    document=doc, relevant=False, rationale=f"Grading failed, excluded by default: {e}"
                ))

        return graded, metadatas

    def rewrite_query(
        self, original_query: str, graded_documents: List[GradedDocument]
    ) -> tuple[RewrittenQuery, LLMCallMetadata]:
        rationales = "\n".join(
            f"- \"{gd.document.content[:120]}...\" -> {'RELEVANT' if gd.relevant else 'NOT relevant'}: {gd.rationale}"
            for gd in graded_documents
        ) or "(no documents were retrieved at all)"

        prompt = f"""The following search query did not retrieve enough relevant knowledge-base documents.

Original query: "{original_query}"

Grading results from the retrieved candidates:
{rationales}

Propose a reformulated search query that is more likely to retrieve genuinely relevant documents. \
Focus on the underlying need expressed in the ticket, using different phrasing/terms than the original query where the grading feedback suggests the original terms were too narrow, too broad, or off-target."""

        result, meta = self.client.generate_structured(
            prompt=prompt,
            schema=RewrittenQuery,
            model=settings.model_grader,
            role="document_grader_rewrite",
            temperature=0.3,
            num_predict=150,
        )
        return result, meta
