"""Domain pack loading against real generated data."""
import glob
import json
import os

from app.domain.loader import list_available_packs, load_domain_pack

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_domain_packs_load():
    packs = list_available_packs()
    assert "it_saas" in packs
    assert "healthcare" in packs

    it = load_domain_pack("it_saas")
    assert it.config.intent_eval_available is True
    assert len(it.config.intents) > 10
    assert len({i.id for i in it.config.intents}) == len(it.config.intents)
    assert glob.glob(os.path.join(it.kb_dir, "*.json"))
    track = next(i for i in it.config.intents if i.id == "track_order")
    assert "invoice" in track.description.lower() or "shipment" in track.description.lower()

    hc = load_domain_pack("healthcare")
    assert hc.config.intent_eval_available is False
    eval_path = os.path.join(REPO_ROOT, "eval", "datasets", "healthcare_test.jsonl")
    with open(eval_path) as f:
        first = json.loads(f.readline())
    assert first["true_intent"] is None
    assert first["real_star_rating"] is not None
