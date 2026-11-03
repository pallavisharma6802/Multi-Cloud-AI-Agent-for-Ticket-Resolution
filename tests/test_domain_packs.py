"""Domain pack loading against real generated data."""
import glob
import os

from app.domain.loader import list_available_packs, load_domain_pack

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_domain_packs_load():
    packs = list_available_packs()
    assert "vscode_support" in packs

    it = load_domain_pack("vscode_support")
    assert it.config.intent_eval_available is False  # no labeled intent benchmark yet
    assert len(it.config.intents) > 10
    assert len({i.id for i in it.config.intents}) == len(it.config.intents)
    assert len(glob.glob(os.path.join(it.kb_dir, "*.json"))) >= 2000
    terminal = next(i for i in it.config.intents if i.id == "terminal")
    assert "terminal" in terminal.description.lower()
