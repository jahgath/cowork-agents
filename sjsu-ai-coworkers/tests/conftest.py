import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from coworkers.llm import LLM  # noqa: E402
from coworkers.memory import Memory  # noqa: E402
from coworkers.profile import load_profile  # noqa: E402

SNAPSHOT = ROOT / "data" / "fixtures" / "articles_snapshot_2026-11-01.json"


@pytest.fixture
def memory():
    return Memory(":memory:")


@pytest.fixture
def profile():
    return load_profile(ROOT / "config" / "profile.yaml")


@pytest.fixture
def offline():
    return LLM("offline")


class FakeLLM:
    """Stands in for Claude/OpenAI so the LLM code paths are tested without a key."""
    provider, model, available = "fake", "fake-1", True

    def __init__(self, response):
        self.response, self.calls = response, 0

    def describe(self):
        return "fake:fake-1"

    def complete_json(self, system, prompt, max_tokens=1500):
        self.calls += 1
        return self.response(prompt) if callable(self.response) else self.response
