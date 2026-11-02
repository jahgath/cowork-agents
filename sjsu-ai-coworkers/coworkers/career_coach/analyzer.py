"""Analyze job descriptions against the learner's measured skill levels."""
from __future__ import annotations

import re

from ..llm import LLM
from ..taxonomy import TOPICS, topic_scores

TARGET_LEVEL = {"internship": 0.65, "research": 0.65, "job": 0.8, "entrepreneurial": 0.6}
STOP = {"intern", "internship", "the", "and", "of", "for", "a", "summer", "2026", "2027", "&", ","}


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z]+", s.lower()) if t not in STOP}


def role_match(title: str, target_roles: list[str]) -> float:
    """How much of a target role appears in the title, discounted by preference order
    (target_roles[0] is the learner's first choice)."""
    t = _tokens(title)
    best = 0.0
    for i, r in enumerate(target_roles):
        rt = _tokens(r)
        if t and rt:
            best = max(best, (len(t & rt) / len(rt)) * (1 - 0.08 * i))
    return best


def required_topics(opp: dict, llm: LLM | None = None) -> dict[str, float]:
    """Topic weights the posting emphasizes. LLM extraction when available, else keyword taxonomy."""
    if llm and llm.available and opp.get("description"):
        data = llm.complete_json(
            "You extract required technical skills from job descriptions.",
            f"Topics: {list(TOPICS)}\nJob description:\n{opp['description'][:6000]}\n"
            'Return JSON {"weights": {topic: importance 0..1}} using only the listed topics.')
        if data and isinstance(data.get("weights"), dict):
            w = {k: float(v) for k, v in data["weights"].items() if k in TOPICS and float(v) > 0}
            total = sum(w.values())
            if total:
                return {k: v / total for k, v in sorted(w.items(), key=lambda kv: -kv[1])}
    return topic_scores(f"{opp['title']} {opp.get('description', '')}")


def analyze(opp: dict, profile: dict, levels: dict[str, float], llm: LLM | None = None) -> dict:
    req = required_topics(opp, llm)
    target = TARGET_LEVEL.get(opp.get("type", "job"), 0.75)
    fit = sum(w * min(1.0, levels.get(t, 0.2) / target) for t, w in req.items()) if req else 0.0
    gaps = sorted(((t, round(w * (target - levels.get(t, 0.2)), 3)) for t, w in req.items()
                   if levels.get(t, 0.2) < target), key=lambda x: -x[1])
    strengths = [t for t, w in req.items() if levels.get(t, 0.2) >= target]
    interest = sum(w * profile.get("interests", {}).get(t, 0.1) for t, w in req.items())
    rm = role_match(opp["title"], profile.get("target_roles", []))
    priority = 0.45 * rm + 0.30 * min(1.0, interest) + 0.25 * fit
    return {**opp, "required": {t: round(w, 3) for t, w in req.items()}, "target_level": target,
            "fit": round(fit, 3), "gaps": gaps, "strengths": strengths, "role_match": round(rm, 3),
            "priority": round(priority, 3)}


def rank(opps: list[dict], profile: dict, levels: dict[str, float], llm: LLM | None = None) -> list[dict]:
    analyzed = [analyze(o, profile, levels, llm) for o in opps]
    return sorted(analyzed, key=lambda a: -a["priority"])
