"""CRAG document grader: LLM relevance checks and query rewrite.

Grades retrieval candidates in one batched LLM call (not one call per doc)
to stay within wall-clock limits on small local models.
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

_LATIN_RATIO_MIN = 0.7


class RelevanceGrade(BaseModel):
    relevant: bool = Field(description="Whether this document's content actually helps resolve the ticket")
    rationale: str = Field(description="One sentence explaining why")


class GradedDocument(BaseModel):
    document: KBDocument
    relevant: bool
    rationale: str


class BatchRelevanceGrades(BaseModel):
    """Flat parallel lists — small local models struggle with list[object] nesting."""
    relevant: List[bool] = Field(description="For each candidate in order: true if relevant")
    rationales: List[str] = Field(description="For each candidate in order: one short sentence")


class RewrittenQuery(BaseModel):
    rewritten_query: str = Field(description="A reformulated English search query more likely to retrieve relevant documents")
    rationale: str = Field(description="Why this reformulation should retrieve better results")


def is_mostly_english(text: str) -> bool:
    """Reject rewrite queries that are mostly non-Latin (e.g. Chinese) scripts."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    latin = sum(1 for c in letters if ("a" <= c.lower() <= "z") or c in "áéíóúüñç")
    return (latin / len(letters)) >= _LATIN_RATIO_MIN and not re.search(r"[\u4e00-\u9fff\u3040-\u30ff\u0400-\u04ff]", text)


class DocumentGrader:
    def __init__(self):
        self.client = get_llm_client()

    def grade_documents(
        self, ticket_text: str, documents: List[KBDocument]
    ) -> tuple[List[GradedDocument], List[LLMCallMetadata]]:
        if not documents:
            return [], []

        metadatas: List[LLMCallMetadata] = []
        doc_blocks = []
        for i, doc in enumerate(documents):
            preview = (doc.content or "")[:500]
            doc_blocks.append(f"[doc_index={i} id={doc.doc_id}]\n{preview}")

        n = len(documents)
        prompt = f"""You are a relevance grader for a support-ticket retrieval system.

Ticket:
{ticket_text}

Candidate knowledge-base documents ({n} total, indexed 0..{n - 1}):
{chr(10).join(doc_blocks)}

Return two parallel lists of length {n}:
- relevant: boolean per document (true only if content would help resolve the ticket)
- rationales: one short sentence per document
Order must match doc_index 0..{n - 1}. Judge substantive overlap, not keyword overlap."""

        try:
            batch, meta = self.client.generate_structured(
                prompt=prompt,
                schema=BatchRelevanceGrades,
                model=settings.model_grader,
                role="document_grader",
                temperature=0.0,
                num_predict=400,
            )
            metadatas.append(meta)
            graded: List[GradedDocument] = []
            for i, doc in enumerate(documents):
                rel = batch.relevant[i] if i < len(batch.relevant) else False
                rat = batch.rationales[i] if i < len(batch.rationales) else "Missing from batch grade response"
                graded.append(GradedDocument(document=doc, relevant=bool(rel), rationale=str(rat)))
            return graded, metadatas
        except RuntimeError as e:
            logger.error(f"batch document_grader failed, falling back to per-doc: {e}")
            return self._grade_documents_sequential(ticket_text, documents)

    def _grade_documents_sequential(
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
Judge based on substantive content overlap, not superficial keyword overlap."""
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
            except RuntimeError as err:
                logger.error(f"document_grader failed for doc {doc.doc_id}: {err}")
                graded.append(GradedDocument(
                    document=doc, relevant=False, rationale=f"Grading failed, excluded by default: {err}"
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

Propose a reformulated search query in English only (ASCII/Latin letters). \
Do not use Chinese, Japanese, Cyrillic, or other non-Latin scripts. \
Focus on the underlying need in the ticket with different phrasing than the original."""

        result, meta = self.client.generate_structured(
            prompt=prompt,
            schema=RewrittenQuery,
            model=settings.model_grader,
            role="document_grader_rewrite",
            temperature=0.3,
            num_predict=150,
        )
        if not is_mostly_english(result.rewritten_query):
            logger.warning(
                f"Rejecting non-English rewrite {result.rewritten_query!r}; keeping original query"
            )
            result = RewrittenQuery(
                rewritten_query=original_query,
                rationale=f"Rejected non-English rewrite; kept original. Model said: {result.rationale}",
            )
        return result, meta
