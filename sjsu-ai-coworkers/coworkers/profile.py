"""Learner profile: interests, self-rated skills, goals. Merged with learned memory."""
from __future__ import annotations

from pathlib import Path

import yaml

from . import DEFAULT_PROFILE
from .memory import Memory


def load_profile(path: str | Path | None = None) -> dict:
    with open(path or DEFAULT_PROFILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def effective_interests(profile: dict, memory: Memory | None = None) -> dict[str, float]:
    """Static interests from the profile + deltas learned from article ratings."""
    interests = dict(profile.get("interests", {}))
    if memory:
        for topic, delta in memory.interest_adjustments().items():
            interests[topic] = max(0.0, min(1.5, interests.get(topic, 0.2) + delta))
    return interests


def skill_levels(profile: dict, memory: Memory | None = None) -> dict[str, float]:
    """0..1 skill level per topic. Measured mastery (from assessments) beats self-rating."""
    levels = {t: v / 5.0 for t, v in profile.get("skills", {}).items()}
    if memory:
        for topic, m in memory.topic_mastery().items():
            self_rated = levels.get(topic)
            # trust measurement more as it accumulates; simple 70/30 blend
            levels[topic] = m if self_rated is None else round(0.7 * m + 0.3 * self_rated, 3)
    return levels
