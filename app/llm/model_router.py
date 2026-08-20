"""Flat per-role Bedrock model ID lookup from settings.

No probing, caching, or auto/unified/manual modes — each role maps to one
``model_*`` setting (Amazon Bedrock model ID).
"""
from __future__ import annotations

from typing import Optional

from app.config import settings

_ROLE_TO_SETTINGS_ATTR = {
    "intent_priority": "model_intent_priority",
    "document_grader": "model_grader",
    "document_grader_rewrite": "model_grader",
    "judge": "model_judge",
    "continuation": "model_continuation",
    "continuation_post_grading": "model_continuation",
    "continuation_post_judging": "model_continuation",
    "drafting": "model_drafting",
    "final_decision": "model_supervisor",
    "security_agent": "model_security_agent",
}


def resolve_model_for_role(role: str, explicit_model: Optional[str] = None) -> str:
    """Return the Bedrock model ID configured for this agent role."""
    if explicit_model:
        return explicit_model
    attr = _ROLE_TO_SETTINGS_ATTR.get(role, "model_supervisor")
    return getattr(settings, attr)


def routing_summary() -> dict:
    """For startup logs / health diagnostics."""
    roles = sorted(set(_ROLE_TO_SETTINGS_ATTR.keys()))
    assignments = {r: resolve_model_for_role(r) for r in roles}
    return {
        "backend": "bedrock",
        "region": settings.aws_region,
        "assignments": assignments,
        "distinct_models": sorted(set(assignments.values())),
    }
