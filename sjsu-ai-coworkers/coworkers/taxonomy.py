"""Shared skill/topic taxonomy.

Both agents speak the same topic vocabulary, which is what lets the career
coach's assessment results steer the daily article recommendations (and vice
versa). Keywords ending in '*' are prefix matches (e.g. 'scalab*' matches
'scalable' and 'scalability'); everything else is a whole-word match.
"""
from __future__ import annotations

import re
from functools import lru_cache

TOPICS: dict[str, list[str]] = {
    "agents": ["agent", "agents", "agentic", "multi-agent", "tool use", "tool calling", "langgraph",
               "orchestrat*", "mcp", "harness", "autonomous", "subagent*", "workflow*"],
    "llm": ["llm", "llms", "language model*", "transformer*", "gpt", "claude", "gemini", "fine-tun*",
            "inference", "token*", "prompt*", "decoding", "attention"],
    "rag": ["retrieval", "rag", "vector*", "embedding*", "semantic search", "rerank*", "knowledge base",
            "chunk*"],
    "evaluation": ["evaluation*", "eval", "evals", "evaluator*", "benchmark*", "llm-as-a-judge",
                   "judge", "metric*", "a/b test*", "ground truth", "observab*", "trace*"],
    "mlops": ["mlops", "deploy*", "ci/cd", "monitoring", "pipeline*", "production", "serving",
              "kubernetes", "docker", "lambda"],
    "system-design": ["scalab*", "architecture", "latency", "throughput", "cach*", "load balanc*",
                      "horizontal*", "monorepo", "infrastructure", "bottleneck*"],
    "distributed-systems": ["distributed", "consensus", "replica*", "replication", "quorum",
                            "shard*", "consistency", "fault toleran*", "durab*"],
    "dev-tools": ["git", "version control", "source control", "ci", "build system*", "code review",
                  "merge*", "commit*", "checkout*", "repository", "repositories"],
    "security": ["security", "sandbox*", "permission*", "prompt injection", "vulnerab*", "privacy",
                 "access control", "containment", "guardrail*", "policy"],
    "python": ["python", "asyncio", "pandas", "numpy", "typescript"],
    "data-structures": ["algorithm*", "data structure*", "hash map", "hashmap", "binary tree",
                        "dynamic programming", "complexity", "big-o"],
    "sql": ["sql", "database*", "postgres*", "query planner", "index*"],
    "startups": ["startup*", "founder*", "venture", "entrepreneur*", "product-market", "go-to-market",
                 "customer*", "pricing", "prototype*"],
    "behavioral": ["leadership", "teamwork", "communication", "conflict", "ownership", "mentor*"],
}

TOPIC_LABELS = {
    "agents": "Agentic AI & orchestration",
    "llm": "LLM fundamentals",
    "rag": "Retrieval-augmented generation",
    "evaluation": "Evaluation & observability",
    "mlops": "MLOps & deployment",
    "system-design": "System design",
    "distributed-systems": "Distributed systems",
    "dev-tools": "Developer tooling & source control",
    "security": "AI security & safety",
    "python": "Python",
    "data-structures": "Data structures & algorithms",
    "sql": "SQL & databases",
    "startups": "Entrepreneurship",
    "behavioral": "Behavioral & communication",
}


@lru_cache(maxsize=None)
def _patterns() -> dict[str, re.Pattern]:
    compiled = {}
    for topic, kws in TOPICS.items():
        parts = []
        for kw in kws:
            if kw.endswith("*"):
                parts.append(r"\b" + re.escape(kw[:-1]))
            else:
                parts.append(r"\b" + re.escape(kw) + r"\b")
        compiled[topic] = re.compile("|".join(parts), re.IGNORECASE)
    return compiled


def topic_counts(text: str) -> dict[str, int]:
    """Raw keyword hit counts per topic."""
    text = text or ""
    out = {}
    for topic, pat in _patterns().items():
        n = len(pat.findall(text))
        if n:
            out[topic] = n
    return out


def topic_scores(text: str) -> dict[str, float]:
    """Topic distribution (weights sum to 1). Empty dict if nothing matched."""
    counts = topic_counts(text)
    total = sum(counts.values())
    if not total:
        return {}
    return {t: c / total for t, c in sorted(counts.items(), key=lambda kv: -kv[1])}


def primary_topic(text: str) -> str | None:
    scores = topic_scores(text)
    return next(iter(scores), None)


def label(topic: str) -> str:
    return TOPIC_LABELS.get(topic, topic)
