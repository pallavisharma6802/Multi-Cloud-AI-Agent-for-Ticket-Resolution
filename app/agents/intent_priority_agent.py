"""LLM intent and priority classification for the active domain pack.

Uses pack taxonomy, priority guidance, Azure NLP signals, and few-shot
examples. Self-consistency sampling reports agreement across multiple draws.
"""
from __future__ import annotations

import logging
import random
from collections import Counter
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.config import settings
from app.domain.schema import DomainPack
from app.llm.ollama_client import LLMCallMetadata, get_llm_client

logger = logging.getLogger(__name__)

PriorityLiteral = Literal["low", "medium", "high", "urgent"]


class IntentPrioritySample(BaseModel):
    intent: str = Field(description="The intent id that best matches the ticket, chosen from the provided taxonomy")
    priority: PriorityLiteral = Field(description="Priority level reasoned from the guidance provided, not a fixed rule")
    rationale: str = Field(description="One or two sentences explaining the reasoning")
    confidence: float = Field(ge=0.0, le=1.0, description="This call's own confidence in its answer")


class IntentPriorityResult(BaseModel):
    intent: str
    category: Optional[str] = None
    priority: PriorityLiteral
    rationale: str
    confidence: float
    self_consistency_agreement: float = Field(
        description="Fraction of self-consistency samples that agreed with the final intent"
    )
    num_samples: int
    known_taxonomy_intent: bool = Field(
        description="Whether the chosen intent id is actually present in the domain pack's taxonomy "
        "(false means the id is not in the pack taxonomy; logged as an anomaly)"
    )


class IntentPriorityAgent:
    def __init__(self, num_samples: int = 3):
        self.client = get_llm_client()
        self.num_samples = num_samples

    def _build_prompt(self, pack: DomainPack, title: str, description: str, signals) -> str:
        intents_block = "\n".join(
            f"- {i.id} (category: {i.category}): {i.description}" for i in pack.config.intents
        )

        fewshot_pool = pack.few_shot_examples
        sampled = random.sample(fewshot_pool, k=min(10, len(fewshot_pool))) if fewshot_pool else []
        fewshot_block = "\n".join(
            f'  Text: "{ex.text}" -> intent: {ex.intent}' for ex in sampled
        ) or "  (no few-shot examples available for this pack)"

        entities_str = ", ".join(e.get("text", "") for e in signals.entities) or "none detected"
        key_phrases_str = ", ".join(signals.key_phrases) or "none extracted"

        return f"""You are the intent and priority classification agent for a "{pack.config.display_name}" support pipeline.

Domain: {pack.config.description}

Available intents (choose exactly one id from this list):
{intents_block}

Priority reasoning guidance (this is advisory reasoning guidance, not a rule table -- use judgment):
{pack.config.priority_guidance}

Illustrative examples from this domain (for calibration only, not exhaustive):
{fewshot_block}

--- Ticket to classify ---
Title: {title}
Description: {description}

Real signals already extracted by Azure Text Analytics (use these, don't re-derive them):
- Entities: {entities_str}
- Sentiment: {signals.sentiment}
- Key phrases: {key_phrases_str}

Classify this ticket's intent (must be one of the ids listed above) and reason about its priority level (low/medium/high/urgent) using the guidance above, not the category name alone. Explain your reasoning briefly."""

    def classify(self, pack: DomainPack, title: str, description: str, signals) -> tuple[IntentPriorityResult, List[LLMCallMetadata]]:
        prompt = self._build_prompt(pack, title, description, signals)
        samples: List[IntentPrioritySample] = []
        metadatas: List[LLMCallMetadata] = []

        for i in range(self.num_samples):
            try:
                sample, meta = self.client.generate_structured(
                    prompt=prompt,
                    schema=IntentPrioritySample,
                    model=settings.model_intent_priority,
                    role="intent_priority",
                    temperature=0.4 if i > 0 else 0.1,
                    num_predict=250,
                )
                samples.append(sample)
                metadatas.append(meta)
            except RuntimeError as e:
                logger.error(f"intent_priority sample {i} failed: {e}")

        if not samples:
            raise RuntimeError("Intent/priority classification failed: all self-consistency samples errored")

        intent_counts = Counter(s.intent for s in samples)
        majority_intent, majority_count = intent_counts.most_common(1)[0]
        agreement = majority_count / len(samples)

        majority_samples = [s for s in samples if s.intent == majority_intent]
        priority_counts = Counter(s.priority for s in majority_samples)
        majority_priority = priority_counts.most_common(1)[0][0]

        representative = max(majority_samples, key=lambda s: s.confidence)
        avg_llm_confidence = sum(s.confidence for s in majority_samples) / len(majority_samples)
        combined_confidence = round((avg_llm_confidence + agreement) / 2, 3)

        known_intents = {i.id: i.category for i in pack.config.intents}
        known = majority_intent in known_intents
        if not known:
            logger.warning(
                f"[intent_priority_agent] LLM chose intent '{majority_intent}' which is NOT in the "
                f"'{pack.config.id}' taxonomy. Recording as-is (anomaly, not silently corrected)."
            )

        result = IntentPriorityResult(
            intent=majority_intent,
            category=known_intents.get(majority_intent),
            priority=majority_priority,
            rationale=representative.rationale,
            confidence=combined_confidence,
            self_consistency_agreement=agreement,
            num_samples=len(samples),
            known_taxonomy_intent=known,
        )
        return result, metadatas
