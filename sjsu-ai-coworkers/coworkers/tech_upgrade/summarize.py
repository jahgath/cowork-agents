"""Turn a ranked article into a learning card.

LLM mode: structured JSON (summary, insights, takeaways, career link, quiz).
Offline mode: extractive summary + topic-aware templates. Both produce the
same schema so the brief renderer and evaluator don't care which ran.
"""
from __future__ import annotations

import re

from ..llm import LLM
from ..taxonomy import TOPICS, label

CAREER_LINKS = {
    "agents": "Agent orchestration (state, tools, loops, human-in-the-loop) is the core skill AI-engineer interviews now probe; this gives you real production patterns to cite.",
    "llm": "Interviewers for ML/AI roles expect you to reason about model behavior, cost and latency trade-offs; this deepens that intuition.",
    "rag": "Most applied-AI internships ship retrieval systems; knowing failure modes and fixes separates you from tutorial-level candidates.",
    "evaluation": "Evaluation is the most under-taught skill in agent engineering and a frequent interview topic; teams hire people who can prove an agent works.",
    "mlops": "Shipping and monitoring models is what turns a demo into a product; this maps directly to production-readiness questions.",
    "system-design": "System-design rounds reward concrete numbers and trade-offs; this article supplies a real case study you can reference.",
    "distributed-systems": "Replication, consistency and quorum trade-offs show up in infra interviews and in any agent platform at scale.",
    "dev-tools": "Agent-era developer tooling (source control, CI, code review) is a fast-growing space for both jobs and startups.",
    "security": "Agent safety (sandboxing, permissions, prompt injection) is becoming a hiring requirement for any team deploying agents.",
    "python": "Strong Python fluency is the baseline for every AI-engineering role you are targeting.",
    "data-structures": "Coding rounds still gate most internships; tie concepts here to the patterns you practice.",
    "sql": "Data access patterns underpin analytics and retrieval features; SQL questions are common in screens.",
    "startups": "Read this as a founder: who has the pain, how is it solved today, and what would an agent-native product do differently?",
}

QUIZ = {
    "agents": "What would break first if this agent design ran 100x more often, and how would you guard against it?",
    "llm": "Which model-level trade-off (quality, latency, cost) does this article optimize, and what does it give up?",
    "rag": "Where in the retrieve-then-generate pipeline does this approach intervene, and how would you measure its effect?",
    "evaluation": "How would you tell the difference between an evaluation that measures real quality and one that is just measuring itself?",
    "mlops": "What would you monitor in production to know this is working, and what would trigger a rollback?",
    "system-design": "Which assumption of the old design stopped holding, and what number made that obvious?",
    "distributed-systems": "Which consistency or durability guarantee is being traded, and who would notice?",
    "dev-tools": "Why do tools built for human-paced development struggle with agent-paced development?",
    "security": "What is the smallest permission set that still lets the agent do its job?",
}

SYSTEM = (
    "You are DailyTechUpgradeAgent, a technical learning coach for a graduate software-engineering "
    "student. You write precise, non-hype summaries of technical articles in your own words. Never "
    "invent numbers, dates or claims that are not in the provided text."
)


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", text or "")
    return [p.strip() for p in parts if 30 <= len(p.strip()) <= 400]


def reading_minutes(article: dict, wpm: int = 230) -> int:
    words = article.get("word_count") or 0
    if words:
        return max(3, min(15, round(words / wpm)))
    return 6  # unknown length: budget a focused skim of the key sections


def offline_card(article: dict, profile: dict) -> dict:
    sents = _sentences(article.get("summary", ""))
    topic = article.get("primary_topic") or "agents"
    kw = re.compile("|".join(re.escape(k.rstrip("*")) for t in article.get("topics", {}) for k in TOPICS[t]), re.I)
    has_number = re.compile(r"\d")

    def weight(i_s):
        i, s = i_s
        return (len(kw.findall(s)) + (1.5 if has_number.search(s) else 0) + (1.0 if i == 0 else 0), -i)

    ranked = [s for _, s in sorted(enumerate(sents), key=weight, reverse=True)]
    summary = " ".join(sents[:2]) if sents else article["title"]
    insights = [s for s in ranked if s not in sents[:2]][:3]
    if not insights:
        insights = ["The available abstract is short. Read the full post for the design details, "
                    "or run with an LLM key so the agent summarizes the full text."]
    takeaways = [
        f"Connect this to {label(topic)}: write a 3-sentence explanation in your own words.",
        "Note one design decision and the trade-off behind it; reuse it as an interview talking point.",
    ]
    return {
        "summary": summary,
        "key_insights": insights,
        "takeaways": takeaways,
        "why_it_matters": CAREER_LINKS.get(topic, CAREER_LINKS["agents"]),
        "career_link": f"Supports your goal ({profile.get('career_goal', 'your next role')}) through {label(topic)}.",
        "quiz_question": QUIZ.get(topic, QUIZ["agents"]),
        "difficulty": "intermediate",
        "generated_by": "offline-extractive",
    }


def llm_card(article: dict, profile: dict, llm: LLM, full_text: str = "") -> dict | None:
    source_text = full_text or article.get("summary", "")
    prompt = f"""Learner profile:
- Program: {profile.get('program')}
- Career goal: {profile.get('career_goal')}; long-term: {profile.get('long_term_goal')}
- Strongest interests: {', '.join(k for k, v in sorted(profile.get('interests', {}).items(), key=lambda kv: -kv[1])[:5])}

Article: "{article['title']}" ({article['source']}, {article.get('published') or 'date unknown'})
URL: {article['url']}
Detected topics: {', '.join(article.get('topics', {}))}

Article text (may be partial):
<<<
{source_text[:9000]}
>>>

Return JSON with keys:
summary (2-3 sentences, your own words),
key_insights (list of exactly 3 concrete technical insights from the text),
takeaways (list of 2 actionable things the learner should do or remember),
why_it_matters (1-2 sentences: how this builds technical knowledge),
career_link (1 sentence tying it to the learner's career goal),
quiz_question (one question that checks real understanding),
difficulty (beginner|intermediate|advanced)."""
    data = llm.complete_json(SYSTEM, prompt)
    if not data or "summary" not in data:
        return None
    data["generated_by"] = llm.describe()
    return data


def make_card(article: dict, profile: dict, llm: LLM | None, full_text: str = "") -> dict:
    card = llm_card(article, profile, llm, full_text) if (llm and llm.available) else None
    card = card or offline_card(article, profile)
    card["reading_minutes"] = reading_minutes(article, profile.get("words_per_minute", 230))
    return {**article, **card}
