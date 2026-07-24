"""Loads and validates the active domain pack from disk."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import List

import yaml

from app.config import settings
from app.domain.schema import DomainPack, DomainPackConfig, FewShotExample


class DomainPackNotFoundError(Exception):
    pass


def _pack_dir(pack_id: str) -> str:
    return os.path.join(settings.domains_root, pack_id)


def list_available_packs() -> List[str]:
    root = settings.domains_root
    if not os.path.isdir(root):
        return []
    return sorted(
        name
        for name in os.listdir(root)
        if os.path.isfile(os.path.join(root, name, "config.yaml"))
    )


def load_domain_pack(pack_id: str) -> DomainPack:
    pack_dir = _pack_dir(pack_id)
    config_path = os.path.join(pack_dir, "config.yaml")
    few_shot_path = os.path.join(pack_dir, "few_shot_examples.json")
    kb_dir = os.path.join(pack_dir, "kb")

    if not os.path.isfile(config_path):
        available = list_available_packs()
        raise DomainPackNotFoundError(
            f"Domain pack '{pack_id}' not found at {config_path}. "
            f"Available packs: {available}"
        )

    with open(config_path, "r") as f:
        raw_config = yaml.safe_load(f)
    config = DomainPackConfig.model_validate(raw_config)

    few_shot_examples: List[FewShotExample] = []
    if os.path.isfile(few_shot_path):
        with open(few_shot_path, "r") as f:
            raw_examples = json.load(f)
        few_shot_examples = [FewShotExample.model_validate(e) for e in raw_examples]

    return DomainPack(config=config, few_shot_examples=few_shot_examples, kb_dir=kb_dir)


@lru_cache(maxsize=8)
def _load_cached(pack_id: str) -> DomainPack:
    return load_domain_pack(pack_id)


def get_active_domain_pack() -> DomainPack:
    """Returns the domain pack selected by settings.domain_pack (cached)."""
    return _load_cached(settings.domain_pack)


def get_domain_pack(pack_id: str) -> DomainPack:
    """Returns a specific pack by id, bypassing the active-settings selection.
    Used by the API when a request explicitly asks for a non-default pack.
    """
    return _load_cached(pack_id)


def clear_cache() -> None:
    _load_cached.cache_clear()
