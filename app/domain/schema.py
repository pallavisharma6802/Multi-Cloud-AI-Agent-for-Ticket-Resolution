"""Schema for domain packs.

A pack supplies taxonomy, priority guidance, KB categories, and provenance for
one business vertical. Agents read settings.domain_pack; they do not hardcode intents.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class SourceDataset(BaseModel):
    """Provenance for the pack's source data. Use limitations when labels are incomplete."""

    name: str
    url: str
    license: str = "unknown"
    real_data: bool = True
    num_source_rows: Optional[int] = None
    limitations: Optional[str] = None


class IntentDefinition(BaseModel):
    id: str
    category: str
    description: str


class FewShotExample(BaseModel):
    text: str
    intent: str
    category: str
    priority_hint: Optional[str] = None


class DomainPackConfig(BaseModel):
    id: str
    display_name: str
    description: str
    source_dataset: SourceDataset
    intents: List[IntentDefinition]
    priority_guidance: str = Field(
        description="Advisory prose for LLM priority reasoning (not a rule table)."
    )
    kb_categories: List[str]
    intent_eval_available: bool = Field(
        default=True,
        description="Whether a labeled intent test set exists for this pack.",
    )


class DomainPack(BaseModel):
    config: DomainPackConfig
    few_shot_examples: List[FewShotExample]
    kb_dir: str
