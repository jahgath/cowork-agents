"""DailyTechUpgradeAgent — LangGraph workflow.

  load_context -> discover -> filter_candidates --(< 6 fresh)--> widen_window --+
                                     |                                           |
                                     +<------------------------------------------+
                                     v
                         score_rank -> select_top3 -> summarize -> compose_brief -> persist
"""
from __future__ import annotations

from datetime import date as Date
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .. import OUTPUT_DIR
from ..llm import LLM
from ..memory import Memory
from ..profile import effective_interests, skill_levels
from .brief import render_brief
from .fetch import fetch_all, fetch_article_text, load_snapshot
from .scoring import age_days, score_article, select_diverse
from .sources import SOURCES
from .summarize import make_card

WINDOW_STEPS = [7, 30, 120, 1095]  # days; widen only when fewer than 3 good candidates


class BriefState(TypedDict, total=False):
    date: str
    profile: dict
    interests: dict
    mastery: dict
    exposure: dict
    seen: list
    candidates: list
    errors: list
    window_idx: int
    filtered: list
    scored: list
    selected: list
    cards: list
    markdown: str
    path: str
    mode: str
    trace: list


def build_tech_upgrade_graph(memory: Memory, llm: LLM, snapshot: str | None = None,
                             out_dir: Path = OUTPUT_DIR, fetch_full_text: bool = True,
                             allow_repeats: bool = False):

    def load_context(state: BriefState) -> BriefState:
        profile = state["profile"]
        levels = skill_levels(profile, memory)
        return {"interests": effective_interests(profile, memory), "mastery": levels,
                "exposure": memory.topic_exposure(), "seen": sorted(memory.seen_urls()),
                "window_idx": 0, "mode": "snapshot" if snapshot else "live",
                "trace": [f"load_context: {len(levels)} skill levels, {len(memory.seen_urls())} past recs"]}

    def discover(state: BriefState) -> BriefState:
        if snapshot:
            arts, errs = load_snapshot(snapshot), []
        else:
            arts, errs = fetch_all(SOURCES, state["profile"])
        return {"candidates": arts, "errors": errs,
                "trace": state["trace"] + [f"discover: {len(arts)} candidates, {len(errs)} source errors"]}

    def filter_candidates(state: BriefState) -> BriefState:
        today = Date.fromisoformat(state["date"])
        window = WINDOW_STEPS[state["window_idx"]]
        seen = set() if allow_repeats else set(state["seen"])
        urls, out = set(), []
        for a in state["candidates"]:
            if not a.get("url") or not a.get("title") or a["url"] in seen or a["url"] in urls:
                continue
            age = age_days(a.get("published"), today)
            if age is not None and age > window:
                continue
            urls.add(a["url"])
            out.append(a)
        return {"filtered": out, "trace": state["trace"] + [f"filter: {len(out)} within {window}d, unseen"]}

    def need_more(state: BriefState) -> str:
        relevant = [a for a in state["filtered"] if a.get("title")]
        if len(relevant) < 6 and state["window_idx"] < len(WINDOW_STEPS) - 1:
            return "widen_window"
        return "score_rank"

    def widen_window(state: BriefState) -> BriefState:
        return {"window_idx": state["window_idx"] + 1,
                "trace": state["trace"] + [f"widen_window -> {WINDOW_STEPS[state['window_idx'] + 1]}d"]}

    def score_rank(state: BriefState) -> BriefState:
        today = Date.fromisoformat(state["date"])
        scored = [score_article(a, state["interests"], state["mastery"], state["exposure"], today)
                  for a in state["filtered"]]
        scored.sort(key=lambda a: -a["score"])
        return {"scored": scored, "trace": state["trace"] + [f"score_rank: top={scored[0]['score'] if scored else 0}"]}

    def select_top3(state: BriefState) -> BriefState:
        sel = select_diverse(state["scored"], k=3)
        return {"selected": sel, "trace": state["trace"] + ["select_top3: " + " | ".join(a["title"][:40] for a in sel)]}

    def summarize(state: BriefState) -> BriefState:
        cards = []
        for a in state["selected"]:
            text = fetch_article_text(a["url"]) if (llm.available and fetch_full_text and not snapshot) else ""
            if text:
                a = {**a, "word_count": len(text.split())}
            cards.append(make_card(a, state["profile"], llm, text))
        return {"cards": cards, "trace": state["trace"] + [f"summarize: {len(cards)} cards via {llm.describe()}"]}

    def compose_brief(state: BriefState) -> BriefState:
        meta = {"mode": state["mode"], "llm": llm.describe(), "n_candidates": len(state["candidates"]),
                "window_days": WINDOW_STEPS[state["window_idx"]], "errors": state.get("errors")}
        return {"markdown": render_brief(state["date"], state["profile"], state["cards"], meta)}

    def persist(state: BriefState) -> BriefState:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"daily_brief_{state['date']}.md"
        path.write_text(state["markdown"], encoding="utf-8")
        memory.record_recommendations(state["date"], state["cards"])
        return {"path": str(path), "trace": state["trace"] + [f"persist: {path.name}"]}

    g = StateGraph(BriefState)
    for name, fn in [("load_context", load_context), ("discover", discover), ("filter_candidates", filter_candidates),
                     ("widen_window", widen_window), ("score_rank", score_rank), ("select_top3", select_top3),
                     ("summarize", summarize), ("compose_brief", compose_brief), ("persist", persist)]:
        g.add_node(name, fn)
    g.add_edge(START, "load_context")
    g.add_edge("load_context", "discover")
    g.add_edge("discover", "filter_candidates")
    g.add_conditional_edges("filter_candidates", need_more, {"widen_window": "widen_window", "score_rank": "score_rank"})
    g.add_edge("widen_window", "filter_candidates")
    g.add_edge("score_rank", "select_top3")
    g.add_edge("select_top3", "summarize")
    g.add_edge("summarize", "compose_brief")
    g.add_edge("compose_brief", "persist")
    g.add_edge("persist", END)
    return g.compile()


def run_daily_brief(profile: dict, memory: Memory, llm: LLM | None = None, date: str | None = None,
                    snapshot: str | None = None, out_dir: Path = OUTPUT_DIR, allow_repeats: bool = False) -> dict:
    llm = llm or LLM()
    graph = build_tech_upgrade_graph(memory, llm, snapshot=snapshot, out_dir=out_dir, allow_repeats=allow_repeats)
    return graph.invoke({"date": date or Date.today().isoformat(), "profile": profile})
