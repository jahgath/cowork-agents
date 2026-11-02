"""Career Readiness Report: scores, strengths, gaps, resources, plan, progress."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from ..taxonomy import label
from .question_bank import BANK, RESOURCES

PROJECTS = {
    "agents": "Add a human-approval interrupt and a step budget to one of your LangGraph agents; write a test that proves the budget stops a runaway loop.",
    "evaluation": "Build a 20-item golden set for one of your agents, score it with a rubric judge, and hand-label 10 items to measure judge agreement.",
    "rag": "Index one course's lecture notes; compare fixed-size vs overlapping chunks by recall@5 on 15 questions you write.",
    "llm": "Measure how temperature and prompt length change cost, latency and accuracy on a 30-question extraction task; plot the trade-off.",
    "system-design": "Write a one-page design doc for 'source control for 1,000 agents' with numbers (QPS, storage, latency budget) and two alternatives.",
    "distributed-systems": "Implement a 3-replica key-value store simulator with configurable W/R quorums and show how one slow replica affects write latency.",
    "mlops": "Containerize an agent API, add request tracing and a token-cost dashboard, and script a canary + rollback.",
    "security": "Red-team your email-reading agent with 10 prompt-injection emails; add least-privilege tools and confirmation gates until all are blocked.",
    "data-structures": "Solve 3 problems per day from one NeetCode pattern; re-solve yesterday's from memory first.",
    "python": "Rewrite a synchronous script that calls an API 50 times using asyncio with a concurrency limit; measure the speed-up.",
    "sql": "Write 10 queries over a public dataset using GROUP BY/HAVING and window functions; EXPLAIN two of them before and after adding an index.",
    "dev-tools": "Set up a merge queue and required checks on a team repo; document the policy for when to rebase versus merge.",
    "behavioral": "Write three STAR stories (learning fast, conflict, failure) with a measurable result each; rehearse aloud in 2 minutes.",
}


def level_label(x: float, coverage: float = 1.0) -> str:
    if coverage < 0.6 and x >= 0.7:
        return "Promising — but less than 60% of the role's skills have been assessed yet"
    if x >= 0.85 and coverage < 0.8:
        return f"Interview-ready with targeted gaps — {1 - coverage:.0%} of the role's skills not yet assessed"
    if x >= 0.85:
        return "Strong — interview-ready"
    if x >= 0.7:
        return "Interview-ready with targeted gaps"
    if x >= 0.5:
        return "Developing — focused practice needed"
    return "Building foundations"


def bar(x: float, width: int = 20) -> str:
    n = round(max(0.0, min(1.0, x)) * width)
    return "█" * n + "░" * (width - n)


def topic_breakdown(results: list[dict]) -> dict[str, float]:
    acc = defaultdict(list)
    for r in results:
        acc[r["topic"]].append(r["score"])
    return {t: round(sum(v) / len(v), 3) for t, v in acc.items()}


def weighted_assessment(topic_avg: dict[str, float], required: dict[str, float]) -> float:
    if not topic_avg:
        return 0.0
    weights = {t: max(required.get(t, 0.0), 0.1) for t in topic_avg}
    return round(sum(topic_avg[t] * w for t, w in weights.items()) / sum(weights.values()), 3)


def study_plan(gap_topics: list[str], start: date, asked: set[str], results: list[dict] | None = None) -> list[str]:
    days, d = [], start
    for i, topic in enumerate(gap_topics[:3]):
        res = next((RESOURCES[r] for q in BANK if q["topic"] == topic for r in q.get("resources", [])), None)
        practice = [q for q in BANK if q["topic"] == topic and q["id"] not in asked]
        weakest = min((r for r in (results or []) if r["topic"] == topic), key=lambda r: r["score"], default=None)
        if practice:
            p = practice[0]["prompt"]
        elif weakest:
            p = f"Re-answer without notes, then compare with the reference: {weakest['prompt']}"
        else:
            p = f"Explain the core ideas of {label(topic)} aloud in 3 minutes, then write them down."
        block = [
            f"Learn: {res[0]} — {res[1]}" if res else f"Learn: core concepts of {label(topic)}",
            f"Practice: {p}",
            f"Build: {PROJECTS.get(topic, 'Apply the concept in a small project.')}",
            "Build (continue) and write a short README explaining your design choices",
            f"Re-assess: `python -m coworkers.cli coach --focus {topic}`",
        ]
        for task in block:
            days.append(f"| {d.isoformat()} | {label(topic)} | {task} |")
            d += timedelta(days=1)
    return days[:14]


def render_report(*, profile: dict, target: dict, ranked: list[dict], results: list[dict], readiness: float,
                  assessment: float, coverage: float, fit_before: float, fit_after: float, topic_avg: dict[str, float],
                  history: list[dict], session_id: str, today: str, llm_desc: str) -> str:
    strengths = [t for t, s in sorted(topic_avg.items(), key=lambda kv: -kv[1]) if s >= 0.75]
    gaps = [t for t, s in sorted(topic_avg.items(), key=lambda kv: kv[1]) if s < 0.6]
    jd_gaps = [t for t, _ in target.get("gaps", []) if t not in gaps and t not in strengths]
    gap_order = gaps + jd_gaps
    asked = {r["qid"] for r in results}

    L = [f"# Career Readiness Report — {today}", "",
         f"{profile.get('name')} · {profile.get('program')} · session `{session_id}`", "",
         "## Summary", "",
         f"Target: **{target['title']}** — {target.get('company')} ({target.get('type')}, {target.get('location')})", "",
         f"Overall readiness: **{readiness:.0%}** — {level_label(readiness, coverage)}", "",
         "| Measure | Score |", "|---|---|",
         f"| Assessment (weighted by what this role asks for) | {assessment:.0%} |",
         f"| Skill fit to job requirements (before this session) | {fit_before:.0%} |",
         f"| Skill fit to job requirements (after this session's evidence) | {fit_after:.0%} |",
         f"| Evidence coverage (share of the role's skill weight assessed so far) | {coverage:.0%} |",
         "", "Readiness = 60% assessment + 40% skill fit (after). Skill levels blend measured mastery with your self-rating, "
         "so a single answer moves an estimate but never sets it outright.", ""]

    L += ["## Opportunities found", "",
          "| Priority | Opportunity | Type | Fit | Top gaps |", "|---|---|---|---|---|"]
    for o in ranked[:6]:
        name = f"[{o['title']}]({o['url']})" if o.get("url") else o["title"]
        gaps_s = ", ".join(label(t) for t, _ in o.get("gaps", [])[:3]) or "—"
        L.append(f"| {o['priority']:.2f} | {name} — {o.get('company')} | {o.get('type')} | {o['fit']:.0%} | {gaps_s} |")
    L.append("")

    L += ["## What this role asks for", "",
          "| Skill area | Weight in posting | Your level now |", "|---|---|---|"]
    for t, w in list(target.get("required", {}).items())[:8]:
        if t in topic_avg:
            now = f"{topic_avg[t]:.0%} (assessed today)"
        else:
            now = f"{target.get('levels', {}).get(t, 0.2):.0%} (self-rating / earlier sessions)"
        L.append(f"| {label(t)} | {w:.0%} | {now} |")
    L.append("")

    L += ["## Assessment results", "",
          "| # | Topic | Type | Level | Score | Feedback |", "|---|---|---|---|---|---|"]
    for i, r in enumerate(results, 1):
        kind = r["kind"] + (" (follow-up)" if r.get("follow_up") else "")
        fb = r["feedback"].replace("|", "/").replace("\n", " ")
        L.append(f"| {i} | {label(r['topic'])} | {kind} | {r['difficulty']}/3 | {r['score']:.0%} | {fb[:220]} |")
    L.append("")

    L += ["## Topic readiness", "", "```"]
    for t, s in sorted(topic_avg.items(), key=lambda kv: -kv[1]):
        L.append(f"{label(t)[:34]:<34} {bar(s)} {s:.0%}")
    L += ["```", "",
          "## Strengths", "",
          *([f"- {label(t)} ({topic_avg[t]:.0%}): keep it warm with one hard question a week." for t in strengths]
            or ["- None at the 75% bar yet. That's normal for a first session."]),
          "", "## Knowledge gaps", ""]
    for t in gap_order[:5]:
        missed = sorted({m for r in results if r["topic"] == t for m in r.get("missed", [])})
        detail = f" Ideas you missed: {', '.join(missed[:6])}." if missed else ""
        src = "from your answers" if t in gaps else "required by the role, not yet demonstrated"
        L.append(f"- **{label(t)}** ({src}).{detail}")
    if not gap_order:
        L.append("- No gaps below 60% this session.")

    L += ["", "## Recommended resources", ""]
    seen = set()
    for t in gap_order[:4]:
        n = 0
        for q in BANK:
            if q["topic"] == t and n < 2:
                for rid in q.get("resources", []):
                    if rid not in seen and rid in RESOURCES and n < 2:
                        seen.add(rid)
                        n += 1
                        L.append(f"- {label(t)}: [{RESOURCES[rid][0]}]({RESOURCES[rid][1]})")
    L += ["", "Your DailyTechUpgradeAgent will now prioritize articles on: "
          + (", ".join(label(t) for t in gap_order[:3]) or "your interests") + ".", ""]

    start = date.fromisoformat(today) + timedelta(days=1)
    L += ["## 14-day preparation plan", "", "| Date | Focus | Task |", "|---|---|---|",
          *study_plan(gap_order or list(topic_avg), start, asked, results), ""]

    L += ["## Progress over time", ""]
    if len(history) > 1:
        L += ["| Session | Date | Target | Readiness | Assessment |", "|---|---|---|---|---|"]
        for h in history:
            L.append(f"| {h['session_id']} | {h['ts'][:10]} | {h['target'][:45]} | {h['readiness']:.0%} | {h['assessment_score']:.0%} |")
        delta = history[-1]["readiness"] - history[-2]["readiness"]
        L += ["", f"Change since last session: **{delta:+.0%}** readiness."]
    else:
        L.append("This is your first session; it becomes the baseline for tracking progress.")
    L += ["", "---", f"Generated by nextLevelPersonalCoachForCareerLevel · grader: {llm_desc} · "
          "coding answers graded by executing unit tests"]
    return "\n".join(L) + "\n"
