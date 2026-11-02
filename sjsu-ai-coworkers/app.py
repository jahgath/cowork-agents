"""Streamlit demo UI for both coworkers.   Run:  streamlit run app.py"""
from datetime import date
from pathlib import Path

import streamlit as st

from coworkers import DEFAULT_DB, OUTPUT_DIR, ROOT
from coworkers.career_coach.graph import CoachSession
from coworkers.llm import LLM
from coworkers.memory import Memory
from coworkers.profile import load_profile
from coworkers.taxonomy import label
from coworkers.tech_upgrade.graph import run_daily_brief

SNAPSHOT = ROOT / "data" / "fixtures" / "articles_snapshot_2026-11-01.json"

st.set_page_config(page_title="SJSU AI Coworkers", page_icon="🎓", layout="wide")
st.markdown("""
<style>
  :root { --sjsu-blue:#0055A2; --sjsu-gold:#E5A823; }
  h1, h2, h3 { color: var(--sjsu-blue); letter-spacing: -0.01em; }
  .stTabs [aria-selected="true"] { border-bottom-color: var(--sjsu-gold) !important; }
  .q-card { border-left: 4px solid var(--sjsu-gold); padding: .75rem 1rem; background: rgba(0,85,162,.05); border-radius: 4px; }
  @media (prefers-color-scheme: dark) { .q-card { background: rgba(229,168,35,.08); } }
</style>""", unsafe_allow_html=True)


@st.cache_resource
def resources():
    return Memory(DEFAULT_DB), LLM(), load_profile()


memory, llm, profile = resources()
st.title("Your AI coworkers")
st.caption(f"{profile['name']} · {profile['program']} · model: {llm.describe()}")

brief_tab, coach_tab, progress_tab = st.tabs(["Daily brief", "Career coach", "Progress"])

# ---------------- Agent 1 ----------------
with brief_tab:
    c1, c2 = st.columns([2, 1])
    live = c2.toggle("Fetch live feeds", value=False, help="Off uses the saved snapshot of real articles (works offline).")
    if c1.button("Build today's brief", type="primary"):
        with st.spinner("Scanning sources and ranking articles…"):
            res = run_daily_brief(profile, memory, llm, date=None if live else "2026-11-01",
                                  snapshot=None if live else str(SNAPSHOT), out_dir=OUTPUT_DIR, allow_repeats=not live)
        st.session_state["brief"] = res
    res = st.session_state.get("brief")
    if res:
        st.markdown(res["markdown"].split("## After reading")[0])
        st.subheader("Rate today's picks")
        for c in res["cards"]:
            cols = st.columns([4, 2, 1])
            cols[0].write(c["title"])
            rating = cols[1].select_slider("Rating", options=[1, 2, 3, 4, 5], value=3, key=f"r_{c['url']}",
                                           label_visibility="collapsed")
            if cols[2].button("Save", key=f"s_{c['url']}"):
                memory.rate(c["url"], rating)
                memory.mark_read(c["url"])
                st.toast(f"Saved. {label(c['primary_topic'])} interest updated.")
    else:
        st.info("Build today's brief to get three articles and a 15–20 minute reading plan.")

# ---------------- Agent 2 ----------------
with coach_tab:
    if "coach" not in st.session_state:
        n = st.slider("Questions in this session", 3, 10, 6)
        if st.button("Start coaching session", type="primary"):
            sess = CoachSession(profile, memory, llm, max_questions=n, today=date.today().isoformat(), out_dir=OUTPUT_DIR)
            st.session_state.update(coach=sess, question=sess.start(), feedback=[])
            st.rerun()
        st.info("The coach finds opportunities, checks your fit, then asks questions and grades your answers.")
    else:
        sess, q = st.session_state["coach"], st.session_state["question"]
        for fb in st.session_state["feedback"][-1:]:
            st.markdown(f"**Last answer: {fb['score']:.0%}** — {fb['feedback']}")
            if fb["score"] < 0.75 and fb.get("reference") and fb["kind"] != "coding":
                with st.expander("Reference answer"):
                    st.write(fb["reference"])
        if q:
            head = "Follow-up challenge" if q["is_follow_up"] else f"Question {q['number']} of {q['of']}"
            st.markdown(f"<div class='q-card'><b>{head}</b> · {q['topic']} · {q['kind']} · difficulty {q['difficulty']}/3"
                        f"<br><br>{q['prompt']}</div>", unsafe_allow_html=True)
            ans = st.text_area("Your answer", height=220 if q["kind"] == "coding" else 140, key=f"a_{q['qid']}_{q['is_follow_up']}",
                               placeholder=f"def {q['func_name']}(...):" if q.get("func_name") else "Explain your reasoning…")
            if st.button("Submit answer", type="primary"):
                st.session_state["question"] = sess.answer(ans or "I don't know")
                st.session_state["feedback"].append(sess.last_result())
                st.rerun()
        else:
            final = sess.graph.get_state(sess.config).values
            st.success(f"Session complete · readiness {final['readiness']:.0%}")
            st.markdown(final["report"])
            st.download_button("Download report (Markdown)", final["report"], file_name=Path(final["report_path"]).name)
            if st.button("Start a new session"):
                for k in ("coach", "question", "feedback"):
                    st.session_state.pop(k, None)
                st.rerun()

# ---------------- Progress ----------------
with progress_tab:
    sessions = memory.sessions()
    if sessions:
        st.subheader("Readiness over time")
        st.line_chart({"readiness": [s["readiness"] for s in sessions], "assessment": [s["assessment_score"] for s in sessions]})
    mastery = memory.topic_mastery()
    if mastery:
        st.subheader("Measured mastery by topic")
        st.bar_chart({label(t): m for t, m in sorted(mastery.items(), key=lambda kv: -kv[1])})
    recs = memory.recommendation_history()
    if recs:
        st.subheader("Reading history")
        st.dataframe([{k: r[k] for k in ("recommended_on", "title", "source", "topic", "rating", "read")} for r in recs])
    if not (sessions or mastery or recs):
        st.info("Progress appears here after your first brief or coaching session.")
