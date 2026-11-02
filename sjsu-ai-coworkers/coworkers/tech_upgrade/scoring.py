"""Personalized ranking.

score = 0.30 relevance      topic match to your interests x content-depth confidence
      + 0.20 authority      editorial prior of the source
      + 0.20 recency        exponential decay, 14-day half-life
      + 0.20 learning_gap   interested in the topic but not yet mastered it
      + 0.10 novelty        topics you have read less about recently

Selection is greedy with diversity penalties (same source / same primary
topic), so the three picks cover different ground.
"""
from __future__ import annotations

import math
from datetime import date

from ..taxonomy import topic_scores

WEIGHTS = {"relevance": 0.30, "authority": 0.20, "recency": 0.20, "learning_gap": 0.20, "novelty": 0.10}
HALF_LIFE_DAYS = 14
DEFAULT_MASTERY = 0.3


def age_days(published: str | None, today: date) -> int | None:
    if not published:
        return None
    try:
        return max(0, (today - date.fromisoformat(published[:10])).days)
    except ValueError:
        return None


def score_article(article: dict, interests: dict, mastery: dict, exposure: dict, today: date) -> dict:
    topics = topic_scores(f"{article['title']} {article['title']} {article.get('summary', '')}")
    if not topics:
        return {**article, "score": 0.0, "topics": {}, "primary_topic": None, "breakdown": {}}

    # depth confidence: a 2-sentence teaser shouldn't beat a substantive article on keyword density
    n_words = len((article.get("summary") or "").split())
    depth = 0.5 + 0.5 * min(1.0, n_words / 120)
    relevance = min(1.0, depth * sum(interests.get(t, 0.1) * w for t, w in topics.items()))
    gap = min(1.0, depth * sum(w * interests.get(t, 0.1) * (1 - mastery.get(t, DEFAULT_MASTERY)) for t, w in topics.items()))
    primary = next(iter(topics))
    novelty = 1.0 / (1.0 + 0.5 * exposure.get(primary, 0.0))
    age = age_days(article.get("published"), today)
    recency = 0.3 if age is None else math.exp(-math.log(2) * age / HALF_LIFE_DAYS)
    parts = {"relevance": relevance, "authority": article.get("authority", 0.5), "recency": recency,
             "learning_gap": gap, "novelty": novelty}
    total = sum(WEIGHTS[k] * v for k, v in parts.items())
    return {**article, "score": round(total, 4), "topics": {t: round(w, 3) for t, w in topics.items()},
            "primary_topic": primary, "age_days": age,
            "depth": round(depth, 3), "breakdown": {k: round(v, 3) for k, v in parts.items()}}


def select_diverse(scored: list[dict], k: int = 3, same_source_penalty: float = 0.12,
                   same_topic_penalty: float = 0.10) -> list[dict]:
    pool = sorted([a for a in scored if a["score"] > 0], key=lambda a: -a["score"])
    chosen: list[dict] = []
    while pool and len(chosen) < k:
        def adjusted(a):
            pen = sum(same_source_penalty for c in chosen if c["org"] == a["org"])
            pen += sum(same_topic_penalty for c in chosen if c["primary_topic"] == a["primary_topic"])
            return a["score"] - pen
        best = max(pool, key=adjusted)
        best = {**best, "adjusted_score": round(adjusted(best), 4)}
        chosen.append(best)
        pool = [a for a in pool if a["url"] != best["url"]]
    return chosen
