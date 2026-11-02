"""nextLevelPersonalCoachForCareerLevel — LangGraph workflow.

load_context -> discover_opportunities -> analyze_fit -> plan_assessment -> select_question
      ^                                                                         |
      |                                                                         v
      |                      +--(follow-up challenge or more questions)--- adapt_difficulty
      |                      |                                                  ^
      +----------------------+       ask (interrupt: waits for the human) -> evaluate_answer
                                                                                |
                                                          (done) -> build_report -> END
"""
from __future__ import annotations

import random
import uuid
from datetime import date as Date
from pathlib import Path
from typing import Any, Callable, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .. import DATA_DIR, OUTPUT_DIR
from ..llm import LLM
from ..memory import Memory
from ..profile import skill_levels
from ..taxonomy import label
from . import analyzer, opportunities
from .evaluator import evaluate
from .question_bank import BANK, generate_question, pick_question, point_labels
from .report import render_report, topic_breakdown, weighted_assessment

SAMPLE_JDS = DATA_DIR / "fixtures" / "sample_jds.json"


class CoachState(TypedDict, total=False):
    session_id: str
    today: str
    profile: dict
    levels: dict
    asked: list
    opportunities: list
    errors: list
    ranked: list
    target: dict
    focus: list
    plan: list
    difficulty: dict
    current: dict
    pending_follow_up: dict | None
    answer: str
    results: list
    n_main: int
    max_questions: int
    followups: int
    report: str
    report_path: str
    readiness: float
    trace: list


def _start_difficulty(level: float) -> int:
    return 1 if level < 0.4 else 2 if level < 0.7 else 3


def build_coach_graph(memory: Memory, llm: LLM, *, sample_path: str | Path | None = SAMPLE_JDS, live: bool = False,
                      out_dir: Path = OUTPUT_DIR, max_followups: int = 2, seed: int = 7, checkpointer=None):
    rng = random.Random(seed)

    def load_context(s: CoachState) -> CoachState:
        levels = skill_levels(s["profile"], memory)
        return {"levels": levels, "asked": sorted(memory.asked_question_ids()), "results": [], "n_main": 0,
                "followups": 0, "pending_follow_up": None, "trace": [f"load_context: {len(levels)} skill levels"]}

    def discover_opportunities(s: CoachState) -> CoachState:
        opps, errs = opportunities.discover(s["profile"], sample_path, live)
        return {"opportunities": opps, "errors": errs, "trace": s["trace"] + [f"discover: {len(opps)} opportunities"]}

    def analyze_fit(s: CoachState) -> CoachState:
        ranked = analyzer.rank(s["opportunities"], s["profile"], s["levels"], llm)
        assessable = [o for o in ranked if o["type"] in ("internship", "job", "research")] or ranked
        target = {**assessable[0], "levels": s["levels"]}
        return {"ranked": ranked, "target": target,
                "trace": s["trace"] + [f"analyze_fit: target='{target['title']}' fit={target['fit']}"]}

    def plan_assessment(s: CoachState) -> CoachState:
        target, levels, n = s["target"], s["levels"], s["max_questions"]
        gaps = [t for t, _ in target["gaps"]]
        focus = s.get("focus") or []
        topics = list(dict.fromkeys(focus + gaps[:3]))
        plan = [{"topic": t, "kind": None} for t in topics]
        # one coding exercise on the most important topic that has one
        asked = set(s["asked"])
        coding_pool = [q for q in BANK if q["kind"] == "coding"]
        unused = [q for q in coding_pool if q["id"] not in asked] or coding_pool
        coding_topic = next((t for t in list(target["required"]) + ["data-structures"]
                             if any(q["topic"] == t for q in unused)), unused[0]["topic"])
        plan.insert(min(2, len(plan)), {"topic": coding_topic, "kind": "coding"})
        strengths = [t for t in target["required"] if t not in topics and t != coding_topic
                     and any(q["topic"] == t for q in BANK)]
        if strengths:
            plan.append({"topic": strengths[0], "kind": None})   # verify a claimed strength
        plan.append({"topic": "behavioral", "kind": "behavioral"})
        if len(plan) > n:  # keep coding + behavioral, trim topic checks
            keep = [p for p in plan if p["kind"] in ("coding", "behavioral")]
            rest = [p for p in plan if p not in keep]
            plan = rest[: max(0, n - len(keep))] + keep
        difficulty = {p["topic"]: _start_difficulty(levels.get(p["topic"], 0.3)) for p in plan}
        return {"plan": plan, "difficulty": difficulty,
                "trace": s["trace"] + ["plan: " + ", ".join(f"{p['topic']}/{p['kind'] or 'auto'}" for p in plan)]}

    def select_question(s: CoachState) -> CoachState:
        if s.get("pending_follow_up"):
            return {"current": s["pending_follow_up"], "pending_follow_up": None,
                    "followups": s["followups"] + 1}
        plan = list(s["plan"])
        exclude = set(s["asked"]) | {r["qid"] for r in s["results"]}
        while plan:
            item = plan.pop(0)
            topic, kind = item["topic"], item["kind"]
            d = s["difficulty"].get(topic, 2)
            q = None
            if llm.available and kind not in ("coding", "behavioral"):
                q = generate_question(topic, d, s["target"].get("description", ""), llm, kind or "concept")
            kinds = [kind] if kind else ["concept", "design"]   # 'auto' slots never become coding
            for k in kinds:
                q = q or pick_question(topic, d, exclude, k, rng)
            q = q or pick_question(topic, d, exclude, None, rng)
            if q is None:  # bank exhausted for this topic: reuse least-recent one rather than skip
                q = pick_question(topic, d, {r["qid"] for r in s["results"]}, kind, rng)
            if q:
                return {"current": {**q, "follow_up_of": None}, "plan": plan, "n_main": s["n_main"] + 1}
        return {"current": None, "plan": []}

    def ask(s: CoachState) -> CoachState:
        q = s["current"]
        answer = interrupt({
            "qid": q["id"], "number": s["n_main"], "of": s["max_questions"], "topic": label(q["topic"]), "kind": q["kind"],
            "difficulty": q["difficulty"], "prompt": q["prompt"], "is_follow_up": bool(q.get("follow_up_of")),
            "func_name": q.get("func_name")})
        return {"answer": str(answer)}

    def evaluate_answer(s: CoachState) -> CoachState:
        q, ans = s["current"], s["answer"]
        g = evaluate(q, ans, llm)
        result = {"qid": q["id"], "topic": q["topic"], "kind": q["kind"], "difficulty": q["difficulty"],
                  "prompt": q["prompt"], "answer": ans, "score": g["score"], "feedback": g["feedback"],
                  "missed": g.get("missed", []), "reference": g.get("reference", ""),
                  "follow_up": bool(q.get("follow_up_of")), "grader": g.get("grader")}
        memory.save_assessment(s["session_id"], {**result, "question": f"[{q['id']}] {q['prompt']}"})
        memory.update_mastery(q["topic"], g["score"], prior=s["levels"].get(q["topic"], 0.3))

        pending = None
        if not q.get("follow_up_of") and 0.3 <= g["score"] < 0.75 and s["followups"] < max_followups:
            fu = q.get("follow_up")
            if g.get("follow_up") and llm.available:   # LLM-generated probe aimed at the biggest gap
                missed = set(g.get("missed", []))
                pts = [p for p, n in zip(q.get("key_points", []), point_labels(q)) if n in missed]
                fu = {"prompt": g["follow_up"], "key_points": pts or q.get("key_points", [])}
            if fu:
                pending = {"id": q["id"] + "-fu", "topic": q["topic"], "kind": q["kind"], "difficulty": q["difficulty"],
                           "prompt": fu["prompt"], "key_points": fu["key_points"], "model_answer": "",
                           "follow_up": None, "follow_up_of": q["id"], "resources": q.get("resources", [])}
        return {"results": s["results"] + [result], "pending_follow_up": pending,
                "trace": s["trace"] + [f"evaluate {q['id']}: {g['score']:.2f}" + (" -> follow-up" if pending else "")]}

    def adapt_difficulty(s: CoachState) -> CoachState:
        last = s["results"][-1]
        d = dict(s["difficulty"])
        cur = d.get(last["topic"], 2)
        d[last["topic"]] = min(3, cur + 1) if last["score"] >= 0.8 else max(1, cur - 1) if last["score"] < 0.4 else cur
        return {"difficulty": d}

    def route(s: CoachState) -> str:
        if s.get("pending_follow_up") or (s["n_main"] < s["max_questions"] and s["plan"]):
            return "select_question"
        return "build_report"

    def has_question(s: CoachState) -> str:
        return "ask" if s.get("current") else "build_report"

    def build_report(s: CoachState) -> CoachState:
        target, profile = s["target"], s["profile"]
        topic_avg = topic_breakdown(s["results"])
        assessment = weighted_assessment(topic_avg, target["required"])
        levels_after = skill_levels(profile, memory)
        fit_after = analyzer.analyze(target, profile, levels_after)["fit"]
        readiness = round(0.6 * assessment + 0.4 * fit_after, 3)
        coverage = round(sum(w for t, w in target["required"].items() if t in topic_avg), 3)
        memory.save_session(s["session_id"], target["title"], readiness, assessment, fit_after, topic_avg, ts=s["today"])
        md = render_report(profile=profile, target=target, ranked=s["ranked"], results=s["results"],
                           readiness=readiness, assessment=assessment, fit_before=target["fit"], fit_after=fit_after,
                           coverage=coverage,
                           topic_avg=topic_avg, history=memory.sessions(), session_id=s["session_id"],
                           today=s["today"], llm_desc=llm.describe())
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"career_readiness_{s['today']}_{s['session_id']}.md"
        path.write_text(md, encoding="utf-8")
        memory.save_session(s["session_id"], target["title"], readiness, assessment, fit_after, topic_avg, str(path), ts=s["today"])
        return {"report": md, "report_path": str(path), "readiness": readiness,
                "trace": s["trace"] + [f"report: readiness={readiness:.2f}"]}

    g = StateGraph(CoachState)
    for name, fn in [("load_context", load_context), ("discover_opportunities", discover_opportunities),
                     ("analyze_fit", analyze_fit), ("plan_assessment", plan_assessment),
                     ("select_question", select_question), ("ask", ask), ("evaluate_answer", evaluate_answer),
                     ("adapt_difficulty", adapt_difficulty), ("build_report", build_report)]:
        g.add_node(name, fn)
    g.add_edge(START, "load_context")
    g.add_edge("load_context", "discover_opportunities")
    g.add_edge("discover_opportunities", "analyze_fit")
    g.add_edge("analyze_fit", "plan_assessment")
    g.add_edge("plan_assessment", "select_question")
    g.add_conditional_edges("select_question", has_question, {"ask": "ask", "build_report": "build_report"})
    g.add_edge("ask", "evaluate_answer")
    g.add_edge("evaluate_answer", "adapt_difficulty")
    g.add_conditional_edges("adapt_difficulty", route, {"select_question": "select_question", "build_report": "build_report"})
    g.add_edge("build_report", END)
    return g.compile(checkpointer=checkpointer or MemorySaver())


class CoachSession:
    """Drive the interrupt/resume loop. Used by the CLI, the Streamlit app and tests."""

    def __init__(self, profile: dict, memory: Memory, llm: LLM | None = None, *, max_questions: int = 6,
                 focus: list[str] | None = None, today: str | None = None, session_id: str | None = None, **graph_kw):
        self.llm = llm or LLM()
        self.graph = build_coach_graph(memory, self.llm, **graph_kw)
        self.session_id = session_id or uuid.uuid4().hex[:8]
        self.config = {"configurable": {"thread_id": self.session_id}}
        self.init = {"session_id": self.session_id, "today": today or Date.today().isoformat(), "profile": profile,
                     "max_questions": max_questions, "focus": focus or []}
        self.state: dict[str, Any] = {}

    def _step(self, payload) -> dict | None:
        self.state = self.graph.invoke(payload, self.config)
        intr = self.state.get("__interrupt__")
        return intr[0].value if intr else None

    def start(self) -> dict | None:
        return self._step(self.init)

    def answer(self, text: str) -> dict | None:
        return self._step(Command(resume=text))

    def last_result(self) -> dict | None:
        res = self.graph.get_state(self.config).values.get("results") or []
        return res[-1] if res else None

    def run(self, answer_fn: Callable[[dict], str], on_feedback: Callable[[dict], None] | None = None) -> dict:
        q = self.start()
        while q is not None:
            q = self.answer(answer_fn(q))
            if on_feedback and (r := self.last_result()):
                on_feedback(r)
        return self.graph.get_state(self.config).values
