"""Render architecture diagrams (Graphviz) and export the compiled LangGraph graphs (Mermaid).

  python scripts/make_diagrams.py     # -> docs/diagrams/*.png, *.svg, *.mmd
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "diagrams"
sys.path.insert(0, str(ROOT))

INK, BLUE, GOLD, PAPER, GREY, GREEN = "#1d2733", "#0b4f8a", "#d9a21b", "#ffffff", "#6b7785", "#2f7d4f"
COMMON = f'''
  graph [fontname="Helvetica", fontsize=13, bgcolor="{PAPER}", pad=0.35, nodesep=0.35, ranksep=0.45, labelloc=t, fontcolor="{INK}"];
  node  [fontname="Helvetica", fontsize=11, shape=box, style="rounded,filled", fillcolor="#eef3f8", color="{BLUE}", fontcolor="{INK}", penwidth=1.2];
  edge  [fontname="Helvetica", fontsize=9, color="{GREY}", fontcolor="{GREY}", arrowsize=0.7];
'''

SYSTEM = f'''digraph G {{ {COMMON}
  label="SJSU Agentic AI Coworkers — system architecture\\n "; rankdir=LR;
  user [label="Student\\n(CLI · Streamlit)", shape=ellipse, fillcolor="#fff6dd", color="{GOLD}"];
  subgraph cluster_a1 {{ label="Agent 1 · DailyTechUpgradeAgent (LangGraph)"; color="{BLUE}"; style=rounded;
    a1 [label="discover → filter → score\\n→ select top 3 → summarize\\n→ daily brief"]; }}
  subgraph cluster_a2 {{ label="Agent 2 · nextLevelPersonalCoachForCareerLevel (LangGraph)"; color="{BLUE}"; style=rounded;
    a2 [label="opportunities → fit & gaps\\n→ plan → ask ⇄ evaluate\\n→ adapt → readiness report"]; }}
  mem [label="Long-term memory (SQLite)\\nrecommendations · ratings\\ntopic mastery · assessments · sessions", shape=cylinder, fillcolor="#e8f4ec", color="{GREEN}"];
  prof [label="Profile (YAML)\\ngoals · interests · skills", shape=note, fillcolor="#f6f6f6", color="{GREY}"];
  llm [label="LLM layer\\nClaude · OpenAI · offline heuristics", shape=component, fillcolor="#f3eefb", color="#6a4fa3"];
  feeds [label="Authoritative feeds\\nOpenAI · Anthropic · Google · Microsoft\\nAWS · IBM · LangChain · GitHub\\nIEEE · ACM · Hugging Face · NVIDIA · arXiv", shape=folder, fillcolor="#f6f6f6", color="{GREY}"];
  jobs [label="Opportunity sources\\nGreenhouse · Lever APIs\\narXiv research leads\\nstartup programs", shape=folder, fillcolor="#f6f6f6", color="{GREY}"];
  sandbox [label="Code runner\\n(subprocess + timeout)", shape=component, fillcolor="#f3eefb", color="#6a4fa3"];
  user -> a1 [label="brief · rate · read"]; user -> a2 [label="answers"];
  a1 -> user [label="Top-3 brief"]; a2 -> user [label="questions · feedback\\nreadiness report"];
  feeds -> a1; jobs -> a2; prof -> a1; prof -> a2;
  a1 -> llm [dir=both]; a2 -> llm [dir=both]; a2 -> sandbox [dir=both, label="coding tests"];
  a1 -> mem [dir=both, label="exposure · ratings"]; a2 -> mem [dir=both, label="mastery · sessions"];
  mem -> a1 [label="gaps steer\\nrecommendations", color="{GOLD}", fontcolor="{GOLD}", penwidth=1.8, constraint=false];
}}'''

AGENT1 = f'''digraph G {{ {COMMON}
  label="Agent 1 · DailyTechUpgradeAgent — workflow, tools, memory\\n "; rankdir=TB;
  start [label="schedule / CLI", shape=ellipse, fillcolor="#fff6dd", color="{GOLD}"];
  load [label="load_context\\ninterests + learned deltas, mastery,\\nexposure, already-seen URLs"];
  disc [label="discover\\nRSS · HTML index · arXiv API\\n(parallel, failures isolated)"];
  filt [label="filter_candidates\\ndedupe · drop seen · recency window"];
  widen [label="widen_window\\n7 → 30 → 120 → 1095 days", fillcolor="#fff6dd", color="{GOLD}"];
  score [label="score_rank\\n0.30 relevance×depth + 0.20 authority\\n+ 0.20 recency + 0.20 learning gap + 0.10 novelty"];
  sel [label="select_top3\\ngreedy with source/topic diversity penalties"];
  summ [label="summarize\\nLLM JSON card (full text) or offline extractive\\nsummary · 3 insights · takeaways · career link · check question"];
  brief [label="compose_brief\\n15–20 min reading plan (Markdown)"];
  persist [label="persist\\nsave brief · record recommendations"];
  mem [label="memory (SQLite)", shape=cylinder, fillcolor="#e8f4ec", color="{GREEN}"];
  fb [label="student feedback\\nrate 1–5 · mark read", shape=ellipse, fillcolor="#fff6dd", color="{GOLD}"];
  start -> load -> disc -> filt;
  filt -> widen [label="< 6 candidates"]; widen -> filt;
  filt -> score [label="enough"]; score -> sel -> summ -> brief -> persist;
  mem -> load [style=dashed]; persist -> mem [style=dashed]; fb -> mem [style=dashed, label="interest deltas · exposure"];
}}'''

AGENT2 = f'''digraph G {{ {COMMON}
  label="Agent 2 · nextLevelPersonalCoachForCareerLevel — workflow, tools, memory\\n "; rankdir=TB;
  start [label="coach session", shape=ellipse, fillcolor="#fff6dd", color="{GOLD}"];
  load [label="load_context\\nskill levels = mastery ⊕ self-rating"];
  disc [label="discover_opportunities\\nGreenhouse · Lever · arXiv · startup programs"];
  fit [label="analyze_fit\\nrequired topics (LLM or taxonomy) · fit · gaps\\npriority = role match + interest + fit"];
  plan [label="plan_assessment\\ngap topics · 1 coding · verify a strength · behavioral"];
  selq [label="select_question\\nLLM-generated from the JD, or bank\\n(nearest difficulty, unused)"];
  ask [label="ask — interrupt()\\nwaits for the student (checkpointed)", fillcolor="#fff6dd", color="{GOLD}"];
  ev [label="evaluate_answer\\ncoding: run unit tests · concepts: LLM rubric or coverage"];
  adapt [label="adapt_difficulty\\n≥ 0.8 harder · < 0.4 easier"];
  rep [label="build_report\\nreadiness · strengths · gaps · resources\\n14-day plan · progress trend"];
  mem [label="memory (SQLite)", shape=cylinder, fillcolor="#e8f4ec", color="{GREEN}"];
  student [label="student", shape=ellipse, fillcolor="#fff6dd", color="{GOLD}"];
  start -> load -> disc -> fit -> plan -> selq -> ask -> ev -> adapt;
  adapt -> selq [label="partial (0.3–0.75): follow-up challenge\\nor more questions"];
  adapt -> rep [label="done"]; selq -> rep [label="bank empty", style=dotted];
  ask -> student [dir=both, style=dashed, label="Command(resume=answer)"];
  ev -> mem [style=dashed, label="assessments · mastery"]; rep -> mem [style=dashed, label="session"];
  mem -> load [style=dashed];
}}'''


def render(name, dot):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.dot").write_text(dot)
    for fmt, extra in (("png", ["-Gdpi=170"]), ("svg", [])):
        subprocess.run(["dot", f"-T{fmt}", *extra, "-o", str(OUT / f"{name}.{fmt}")], input=dot.encode(), check=True)
    print("rendered", name)


if __name__ == "__main__":
    render("system_architecture", SYSTEM)
    render("agent1_tech_upgrade", AGENT1)
    render("agent2_career_coach", AGENT2)
    from coworkers.career_coach.graph import build_coach_graph
    from coworkers.llm import LLM
    from coworkers.memory import Memory
    from coworkers.tech_upgrade.graph import build_tech_upgrade_graph
    m, llm = Memory(), LLM("offline")
    (OUT / "langgraph_tech_upgrade.mmd").write_text(build_tech_upgrade_graph(m, llm, snapshot="x").get_graph().draw_mermaid())
    (OUT / "langgraph_career_coach.mmd").write_text(build_coach_graph(m, llm).get_graph().draw_mermaid())
    print("exported LangGraph mermaid graphs")
