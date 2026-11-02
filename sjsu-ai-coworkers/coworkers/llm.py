"""Provider-agnostic LLM wrapper.

Order of preference (override with COWORKER_LLM=anthropic|openai|offline):
  1. Anthropic (ANTHROPIC_API_KEY)
  2. OpenAI    (OPENAI_API_KEY)
  3. Offline   deterministic heuristics, so the whole project runs and is
               testable with no key, no network and no cost.

Every caller checks `llm.available` and falls back to a heuristic path, so the
agents degrade gracefully instead of failing.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

DEFAULT_MODELS = {
    "anthropic": os.getenv("COWORKER_ANTHROPIC_MODEL", "claude-sonnet-5-5"),
    "openai": os.getenv("COWORKER_OPENAI_MODEL", "gpt-4.1-mini"),
}


class LLM:
    def __init__(self, provider: str | None = None, model: str | None = None):
        provider = (provider or os.getenv("COWORKER_LLM", "auto")).lower()
        if provider == "auto":
            if os.getenv("ANTHROPIC_API_KEY"):
                provider = "anthropic"
            elif os.getenv("OPENAI_API_KEY"):
                provider = "openai"
            else:
                provider = "offline"
        self.provider = provider
        self.model = model or DEFAULT_MODELS.get(provider, "offline")
        self._client = None
        self.calls = 0

    @property
    def available(self) -> bool:
        return self.provider in ("anthropic", "openai")

    def describe(self) -> str:
        return f"{self.provider}:{self.model}" if self.available else "offline (heuristic mode)"

    # -- raw completion -------------------------------------------------
    def complete(self, system: str, prompt: str, max_tokens: int = 1500, temperature: float = 0.2) -> str:
        if not self.available:
            raise RuntimeError("No LLM provider configured; caller should use the offline path.")
        self.calls += 1
        if self.provider == "anthropic":
            if self._client is None:
                import anthropic  # lazy import: optional dependency
                self._client = anthropic.Anthropic()
            resp = self._client.messages.create(
                model=self.model, max_tokens=max_tokens, temperature=temperature,
                system=system, messages=[{"role": "user", "content": prompt}],
            )
            return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        if self.provider == "openai":
            if self._client is None:
                from openai import OpenAI  # lazy import: optional dependency
                self._client = OpenAI()
            resp = self._client.chat.completions.create(
                model=self.model, max_tokens=max_tokens, temperature=temperature,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            )
            return resp.choices[0].message.content or ""
        raise ValueError(f"Unknown provider {self.provider}")

    # -- structured completion -----------------------------------------
    def complete_json(self, system: str, prompt: str, max_tokens: int = 1500) -> dict[str, Any] | None:
        """Ask for JSON; return None (never raise) if the provider or parsing fails."""
        if not self.available:
            return None
        system = system + "\nRespond with ONLY a valid JSON object. No markdown fences, no commentary."
        try:
            return parse_json(self.complete(system, prompt, max_tokens=max_tokens))
        except Exception:  # network errors, rate limits, bad JSON -> fall back
            return None


def parse_json(text: str) -> dict[str, Any] | None:
    text = re.sub(r"```(?:json)?", "", text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None
