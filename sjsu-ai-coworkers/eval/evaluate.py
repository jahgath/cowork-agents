"""Evaluation harness for both coworkers.

  python -m eval.evaluate            # writes eval/results.json and eval/EVAL_RESULTS.md

Agent 1 (DailyTechUpgradeAgent)
  nDCG@3 vs author relevance labels, compared with recency-only and random baselines
  source authority rate, org/topic diversity, freshness, session length, insight grounding,
  personalization responsiveness (does a rating change tomorrow's ranking?)
Agent 2 (nextLevelPersonalCoachForCareerLevel)
  grader-human agreement (MAE, Spearman, within-0.25), coding-grader mutation detection,
  question relevance to the target role, adaptivity, readiness change across sessions
"""
from __future__ import annotations

import json
import math
import random
import re
import statistics
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from coworkers.career_coach.evaluator import evaluate, run_code_tests  # noqa: E402
from coworkers.career_coach.graph import CoachSession  # noqa: E402
from coworkers.career_coach.question_bank import BY_ID  # noqa: E402
from coworkers.llm import LLM  # noqa: E402
from coworkers.memory import Memory  # noqa: E402
from coworkers.profile import effective_interests, load_profile, skill_levels  # noqa: E402
from coworkers.tech_upgrade.fetch import load_snapshot  # noqa: E402
from coworkers.tech_upgrade.graph import run_daily_brief  # noqa: E402
from coworkers.tech_upgrade.scoring import score_article, select_diverse  # noqa: E402
from coworkers.tech_upgrade.sources import AUTHORITATIVE_ORGS  # noqa: E402

FIX = ROOT / "data" / "fixtures"
SNAP = FIX / "articles_snapshot_2026-11-01.json"
TODAY = "2026-11-01"
STOP = set("the a an and or of to in on for with is are was were be by as at it its this that from into than then so".split())


def ndcg_at_k(ranked_urls, labels, k=3):
    dcg = sum((2 ** labels.get(u, 0) - 1) / math.log2(i + 2) for i, u in enumerate(ranked_urls[:k]))
    ideal = sorted(labels.values(), reverse=True)[:k]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def spearman(x, y):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for t in range(i, j + 1):
                r[order[t]] = (i + j) / 2
            i = j + 1
        return r
    rx, ry = ranks(x), ranks(y)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else 0.0


def grounded(sentence, source):
    words = [w for w in re.findall(r"[a-z0-9]+", sentence.lower()) if w not in STOP and len(w) > 2]
    src = set(re.findall(r"[a-z0-9]+", source.lower()))
    return not words or sum(w in src for w in words) / len(words) >= 0.7


def eval_agent1(profile, llm):
    labels = json.loads((ROOT / "data/eval/article_relevance_labels.json").read_text())["labels"]
    mem = Memory(":memory:")
    with tempfile.TemporaryDirectory() as tmp:
        res = run_daily_brief(profile, mem, llm, date=TODAY, snapshot=str(SNAP), out_dir=Path(tmp))
    cards = res["cards"]
    picked = [c["url"] for c in cards]

    arts = load_snapshot(SNAP)
    by_recency = sorted(arts, key=lambda a: a.get("published") or "0000", reverse=True)
    rng = random.Random(0)
    random_ndcg = statistics.mean(ndcg_at_k([a["url"] for a in rng.sample(arts, len(arts))], labels) for _ in range(500))

    src = {a["url"]: a["summary"] for a in arts}
    insights = [(s, src[c["url"]]) for c in cards for s in c["key_insights"] if not s.startswith("The available abstract")]
    ages = [c["age_days"] for c in cards if c.get("age_days") is not None]
    minutes = sum(int(m) for m in re.findall(r"\| (\d+) \|\n", res["markdown"]))

    # personalization responsiveness: love evaluation, dislike dev-tools -> re-rank
    d = date.fromisoformat(TODAY)
    def rank_of(memory, title_part):
        sc = [score_article(a, effective_interests(profile, memory), skill_levels(profile, memory), {}, d) for a in arts]
        order = [a["title"] for a in sorted(sc, key=lambda a: -a["score"])]
        return next(i for i, t in enumerate(order) if title_part in t) + 1
    m2 = Memory(":memory:")
    m2.record_recommendations(TODAY, [{**c, "score": c["score"]} for c in cards])
    before = rank_of(m2, "AgentCore Evaluations")
    for c in cards:
        m2.rate(c["url"], 5 if c["primary_topic"] == "evaluation" else 1 if c["primary_topic"] == "dev-tools" else 3)
    after = rank_of(m2, "AgentCore Evaluations")

    return {
        "picked": [c["title"] for c in cards],
        "ndcg@3": round(ndcg_at_k(picked, labels), 3),
        "ndcg@3_recency_baseline": round(ndcg_at_k([a["url"] for a in by_recency], labels), 3),
        "ndcg@3_random_baseline": round(random_ndcg, 3),
        "authority_rate": sum(c["org"] in AUTHORITATIVE_ORGS for c in cards) / len(cards),
        "distinct_orgs": len({c["org"] for c in cards}),
        "distinct_topics": len({c["primary_topic"] for c in cards}),
        "median_age_days": statistics.median(ages) if ages else None,
        "session_minutes": minutes,
        "insight_grounding_rate": round(sum(grounded(s, t) for s, t in insights) / max(1, len(insights)), 3),
        "rated_topic_rank_before": before, "rated_topic_rank_after": after,
        "summarizer": llm.describe(),
    }


MUTANTS = {
    "code-1": "def two_sum(nums, target):\n    for i in range(len(nums)):\n        for j in range(len(nums)):\n            if nums[i] + nums[j] == target:\n                return [i, j]\n    return []",
    "code-2": "def chunk_text(text, size, overlap):\n    w = text.split()\n    return [' '.join(w[i:i+size]) for i in range(0, len(w), size - overlap)]",
    "code-3": "def cosine_top_k(query, docs, k):\n    dots = [sum(a*b for a, b in zip(query, d)) for d in docs]\n    return sorted(range(len(docs)), key=lambda i: -dots[i])[:k]",
    "code-4": "def topo_order(deps):\n    return sorted(deps, key=lambda t: len(deps[t]))",
}


def eval_agent2(profile, llm):
    items = json.loads((ROOT / "data/eval/grader_labels.json").read_text())["items"]
    auto = [evaluate(BY_ID[it["qid"]], it["answer"], llm)["score"] for it in items]
    human = [it["human"] for it in items]
    err = [abs(a - h) for a, h in zip(auto, human)]

    mutants = {qid: run_code_tests(code, BY_ID[qid]["func_name"], BY_ID[qid]["tests"]) for qid, code in MUTANTS.items()}
    refs = {qid: run_code_tests(BY_ID[qid]["model_answer"], BY_ID[qid]["func_name"], BY_ID[qid]["tests"]) for qid in MUTANTS}

    a1 = json.loads((FIX / "session1_answers.json").read_text())
    a2 = json.loads((FIX / "session2_answers.json").read_text())
    mem = Memory(":memory:")
    with tempfile.TemporaryDirectory() as tmp:
        s1 = CoachSession(profile, mem, llm, today="2026-11-01", session_id="e1", out_dir=Path(tmp)).run(lambda q: a1.get(q["qid"], "I don't know"))
        s2 = CoachSession(profile, mem, llm, today="2026-11-08", session_id="e2", out_dir=Path(tmp)).run(lambda q: a2.get(q["qid"], "I don't know"))
    req = s1["target"]["required"]
    tech = [r for r in s1["results"] + s2["results"] if r["kind"] != "behavioral"]
    diffs = {(r["topic"], r["difficulty"]) for r in s1["results"]}
    return {
        "grader": "unit tests (coding) + " + (llm.describe() if llm.available else "rubric coverage (offline)"),
        "n_labeled": len(items),
        "grader_mae": round(statistics.mean(err), 3),
        "grader_within_0.25": round(sum(e <= 0.25 for e in err) / len(err), 3),
        "grader_spearman": round(spearman(auto, human), 3),
        "worst_disagreements": sorted(({"qid": it["qid"], "human": it["human"], "auto": a} for it, a in zip(items, auto)),
                                      key=lambda x: -abs(x["human"] - x["auto"]))[:3],
        "reference_solutions_pass": all(r["passed"] == r["total"] for r in refs.values()),
        "mutants_detected": f"{sum(m['passed'] < m['total'] for m in mutants.values())}/{len(mutants)}",
        "question_relevance": round(sum(r["topic"] in req for r in tech) / len(tech), 3),
        "follow_ups_asked": sum(r["follow_up"] for r in s1["results"] + s2["results"]),
        "distinct_topic_difficulty_pairs_s1": len(diffs),
        "readiness_s1": s1["readiness"], "readiness_s2": s2["readiness"],
        "target": s1["target"]["title"],
    }


def to_markdown(r1, r2):
    L = ["# Evaluation results", "", "Generated by `python -m eval.evaluate`. Offline mode unless an API key is set.", "",
         "## Agent 1 — DailyTechUpgradeAgent", "",
         f"Picks: {'; '.join(r1['picked'])}", "",
         "| Metric | Value | Target |", "|---|---|---|",
         f"| nDCG@3 vs labeled relevance | {r1['ndcg@3']:.2f} | ≥ 0.80 |",
         f"| nDCG@3, recency-only baseline | {r1['ndcg@3_recency_baseline']:.2f} | (comparison) |",
         f"| nDCG@3, random baseline (500 draws) | {r1['ndcg@3_random_baseline']:.2f} | (comparison) |",
         f"| Picks from authoritative sources | {r1['authority_rate']:.0%} | 100% |",
         f"| Distinct organizations / topics in top 3 | {r1['distinct_orgs']} / {r1['distinct_topics']} | 3 / ≥ 2 |",
         f"| Median age of picks (days) | {r1['median_age_days']} | informational |",
         f"| Planned session length (min) | {r1['session_minutes']} | 15–20 |",
         f"| Insight sentences grounded in source text | {r1['insight_grounding_rate']:.0%} | ≥ 90% |",
         f"| Rank of evaluation article before → after ratings | {r1['rated_topic_rank_before']} → {r1['rated_topic_rank_after']} | moves up |",
         "", "## Agent 2 — nextLevelPersonalCoachForCareerLevel", "",
         f"Grader: {r2['grader']}. Target role: {r2['target']}.", "",
         "| Metric | Value | Target |", "|---|---|---|",
         f"| Grader mean absolute error vs human ({r2['n_labeled']} labeled answers) | {r2['grader_mae']:.2f} | ≤ 0.20 |",
         f"| Grader within ±0.25 of human | {r2['grader_within_0.25']:.0%} | ≥ 80% |",
         f"| Grader rank correlation (Spearman) | {r2['grader_spearman']:.2f} | ≥ 0.70 |",
         f"| Reference coding solutions pass | {'yes' if r2['reference_solutions_pass'] else 'NO'} | yes |",
         f"| Buggy coding solutions detected | {r2['mutants_detected']} | all |",
         f"| Technical questions on the role's required topics | {r2['question_relevance']:.0%} | ≥ 80% |",
         f"| Follow-up challenges asked (2 sessions) | {r2['follow_ups_asked']} | ≥ 1 |",
         f"| Readiness, session 1 → session 2 | {r2['readiness_s1']:.0%} → {r2['readiness_s2']:.0%} | increases |",
         "", "Largest grader–human disagreements:", ""]
    L += [f"- `{d['qid']}`: human {d['human']:.2f}, grader {d['auto']:.2f}" for d in r2["worst_disagreements"]]
    return "\n".join(L) + "\n"


def main():
    profile, llm = load_profile(), LLM()
    r1, r2 = eval_agent1(profile, llm), eval_agent2(profile, llm)
    out = ROOT / "eval"
    (out / "results.json").write_text(json.dumps({"agent1": r1, "agent2": r2}, indent=2))
    md = to_markdown(r1, r2)
    (out / "EVAL_RESULTS.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
