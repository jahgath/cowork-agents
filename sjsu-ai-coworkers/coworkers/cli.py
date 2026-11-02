"""Command-line entry point.

  python -m coworkers.cli brief                      # Agent 1: today's top-3 brief (live feeds)
  python -m coworkers.cli brief --snapshot FILE      # offline / reproducible run
  python -m coworkers.cli rate URL 5                 # feedback -> personalization
  python -m coworkers.cli read URL                   # mark read -> learning progress
  python -m coworkers.cli coach                      # Agent 2: interactive coaching session
  python -m coworkers.cli coach --answers FILE.json  # scripted session (demos, tests)
  python -m coworkers.cli opportunities [--live]     # ranked opportunities + fit
  python -m coworkers.cli progress                   # readiness + mastery over time
  python -m coworkers.cli graphs                     # export LangGraph diagrams (Mermaid)
  python -m coworkers.cli sources --check            # verify feed URLs still work
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import DEFAULT_DB, OUTPUT_DIR, ROOT
from .llm import LLM
from .memory import Memory
from .profile import load_profile, skill_levels
from .taxonomy import label


def _read_multiline(prompt_kind: str) -> str:
    end_hint = "finish with a line containing only END" if prompt_kind == "coding" else "finish with an empty line"
    print(f"  (Your answer — {end_hint}. Type 'idk' to skip.)")
    lines = []
    while True:
        try:
            line = input("  > " if not lines else "    ")
        except EOFError:
            break
        if prompt_kind == "coding" and line.strip() == "END":
            break
        if prompt_kind != "coding" and not line.strip():
            break
        lines.append(line)
    return "\n".join(lines)


def cmd_brief(a, mem, llm, profile):
    from .tech_upgrade.graph import run_daily_brief
    res = run_daily_brief(profile, mem, llm, date=a.date, snapshot=a.snapshot, out_dir=Path(a.out),
                          allow_repeats=a.allow_repeats)
    print(res["markdown"])
    print(f"\nSaved: {res['path']}", file=sys.stderr)
    if a.verbose:
        print("\n".join(res["trace"]), file=sys.stderr)


def cmd_rate(a, mem, *_):
    topic = mem.rate(a.url, a.rating)
    print(f"Thanks — rating saved. Interest in '{label(topic)}' adjusted." if topic else "URL not found in history.")


def cmd_read(a, mem, *_):
    mem.mark_read(a.url)
    print("Marked as read; topic exposure updated.")


def cmd_coach(a, mem, llm, profile):
    from .career_coach.graph import CoachSession
    scripted = json.loads(Path(a.answers).read_text()) if a.answers else None
    transcript = []

    def answer_fn(q):
        tag = "Follow-up challenge" if q["is_follow_up"] else f"Question {q['number']} of {q['of']}"
        print(f"\n{'─' * 72}\n{tag} · {q['topic']} · {q['kind']} · difficulty {q['difficulty']}/3\n")
        print(q["prompt"])
        if q.get("func_name"):
            print(f"  (Define a Python function named `{q['func_name']}`; it will be run against hidden tests.)")
        if scripted is not None:
            ans = scripted.get(q["qid"], "I don't know")
            print("\n  > " + ans.replace("\n", "\n    "))
        else:
            ans = _read_multiline(q["kind"])
        transcript.append({"q": q, "answer": ans})
        return ans

    def on_feedback(r):
        print(f"\n  Score: {r['score']:.0%}  ·  graded by {r['grader']}\n  Feedback: {r['feedback']}")
        if r["score"] < 0.75 and r.get("reference") and r["kind"] != "coding":
            print(f"  Reference answer: {r['reference']}")
        transcript[-1]["result"] = r

    session = CoachSession(profile, mem, llm, max_questions=a.questions, focus=a.focus.split(",") if a.focus else None,
                           today=a.date, session_id=a.session_id, live=a.live, out_dir=Path(a.out))
    print(f"nextLevelPersonalCoachForCareerLevel · session {session.session_id} · grader: {llm.describe()}")
    state = session.run(answer_fn, on_feedback)
    t = state["target"]
    print(f"\n{'═' * 72}\nTarget: {t['title']} — {t['company']}  ·  readiness {state['readiness']:.0%}")
    print(f"Full report: {state['report_path']}")
    if a.transcript:
        write_transcript(Path(a.transcript), session.session_id, state, transcript, llm)
        print(f"Transcript: {a.transcript}")


def write_transcript(path: Path, sid: str, state: dict, transcript: list, llm: LLM):
    t = state["target"]
    L = [f"# Interactive coaching session `{sid}` — {state['today']}", "",
         f"Target opportunity: **{t['title']}** — {t['company']}. Grader: {llm.describe()}; coding answers run against unit tests.", ""]
    for turn in transcript:
        q, r = turn["q"], turn.get("result", {})
        head = "Follow-up challenge" if q["is_follow_up"] else f"Question {q['number']} of {q['of']}"
        L += [f"## {head} · {q['topic']} · {q['kind']} · difficulty {q['difficulty']}/3", "",
              f"**Coach:** {q['prompt']}", ""]
        if q["kind"] == "coding":
            L += ["**Student:**", "", "```python", turn["answer"], "```", ""]
        else:
            L += [f"**Student:** {turn['answer']}", ""]
        if r:
            L += [f"**Coach evaluation:** {r['score']:.0%}. {r['feedback']}", ""]
            if r["score"] < 0.75 and r.get("reference") and r["kind"] != "coding":
                L += [f"**Reference answer:** {r['reference']}", ""]
    L += ["## Session outcome", "", f"Readiness for this target: **{state['readiness']:.0%}**. "
          f"Full report: `{Path(state['report_path']).name}`.", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L), encoding="utf-8")


def cmd_opportunities(a, mem, llm, profile):
    from .career_coach import analyzer, opportunities
    from .career_coach.graph import SAMPLE_JDS
    opps, errs = opportunities.discover(profile, None if a.no_samples else SAMPLE_JDS, a.live)
    for o in analyzer.rank(opps, profile, skill_levels(profile, mem), llm):
        gaps = ", ".join(label(t) for t, _ in o["gaps"][:3]) or "—"
        print(f"{o['priority']:.2f}  fit {o['fit']:.0%}  [{o['type']}] {o['title']} — {o['company']}\n      gaps: {gaps}"
              + (f"\n      {o['url']}" if o.get("url") else ""))
    for e in errs:
        print("  source error:", e, file=sys.stderr)


def cmd_progress(a, mem, llm, profile):
    sessions = mem.sessions()
    print("Coaching sessions:")
    for s in sessions:
        print(f"  {s['ts'][:16]}  {s['session_id']}  readiness {s['readiness']:.0%}  assessment {s['assessment_score']:.0%}  {s['target'][:50]}")
    if not sessions:
        print("  none yet — run `coach`.")
    print("\nTopic mastery (from assessments) and reading exposure:")
    exp = mem.topic_exposure()
    for t, m in sorted(mem.topic_mastery().items(), key=lambda kv: -kv[1]):
        print(f"  {label(t):<36} mastery {m:.0%}   reading exposure {exp.get(t, 0):.1f}")
    recs = mem.recommendation_history()
    rated = [r for r in recs if r["rating"]]
    print(f"\nArticles recommended: {len(recs)} · read: {sum(r['read'] for r in recs)} · rated: {len(rated)}"
          + (f" · avg rating {sum(r['rating'] for r in rated) / len(rated):.1f}/5" if rated else ""))


def cmd_graphs(a, mem, llm, profile):
    from .career_coach.graph import build_coach_graph
    from .tech_upgrade.graph import build_tech_upgrade_graph
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, g in [("tech_upgrade_graph", build_tech_upgrade_graph(mem, llm, snapshot="x")),
                    ("career_coach_graph", build_coach_graph(mem, llm))]:
        (out / f"{name}.mmd").write_text(g.get_graph().draw_mermaid(), encoding="utf-8")
        print(f"wrote {out / (name + '.mmd')}")


def cmd_sources(a, *_):
    from .tech_upgrade.fetch import fetch_all
    from .tech_upgrade.sources import SOURCES
    for s in SOURCES:
        arts, errs = fetch_all([s], {"research_interests": ["LLM agents"]}, per_source=3)
        status = f"OK ({len(arts)} items)" if arts else ("FAIL " + errs[0] if errs else "EMPTY")
        print(f"{s['name']:<34} {status}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="coworkers", description="SJSU Agentic AI Coworkers")
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--profile", default=None)
    p.add_argument("--llm", default=None, help="anthropic | openai | offline (default: auto)")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("brief"); b.add_argument("--snapshot"); b.add_argument("--date")
    b.add_argument("--out", default=str(OUTPUT_DIR)); b.add_argument("--allow-repeats", action="store_true")
    b.add_argument("-v", "--verbose", action="store_true")
    r = sub.add_parser("rate"); r.add_argument("url"); r.add_argument("rating", type=int, choices=range(1, 6))
    rd = sub.add_parser("read"); rd.add_argument("url")
    c = sub.add_parser("coach"); c.add_argument("--questions", type=int, default=6); c.add_argument("--focus")
    c.add_argument("--answers"); c.add_argument("--live", action="store_true"); c.add_argument("--date")
    c.add_argument("--session-id"); c.add_argument("--transcript"); c.add_argument("--out", default=str(OUTPUT_DIR))
    o = sub.add_parser("opportunities"); o.add_argument("--live", action="store_true"); o.add_argument("--no-samples", action="store_true")
    sub.add_parser("progress")
    g = sub.add_parser("graphs"); g.add_argument("--out", default=str(ROOT / "docs" / "diagrams"))
    s = sub.add_parser("sources"); s.add_argument("--check", action="store_true")

    a = p.parse_args(argv)
    mem, llm = Memory(a.db), LLM(a.llm)
    profile = load_profile(a.profile)
    {"brief": cmd_brief, "rate": cmd_rate, "read": cmd_read, "coach": cmd_coach, "opportunities": cmd_opportunities,
     "progress": cmd_progress, "graphs": cmd_graphs, "sources": cmd_sources}[a.cmd](a, mem, llm, profile)


if __name__ == "__main__":
    main()
