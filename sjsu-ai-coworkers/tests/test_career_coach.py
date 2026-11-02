import json

from conftest import ROOT, FakeLLM
from coworkers.career_coach.analyzer import analyze, role_match
from coworkers.career_coach.evaluator import evaluate, run_code_tests
from coworkers.career_coach.graph import CoachSession
from coworkers.career_coach.question_bank import BANK, BY_ID
from coworkers.profile import skill_levels

ANS1 = json.loads((ROOT / "data/fixtures/session1_answers.json").read_text())
ANS2 = json.loads((ROOT / "data/fixtures/session2_answers.json").read_text())


def test_every_reference_solution_passes_its_tests():
    for q in BANK:
        if q["kind"] == "coding":
            res = run_code_tests(q["model_answer"], q["func_name"], q["tests"])
            assert res["passed"] == res["total"], q["id"]


def test_code_grader_handles_bugs_loops_and_syntax_errors():
    q = BY_ID["code-2"]
    buggy = "def chunk_text(t, s, o):\n    w = t.split()\n    return [' '.join(w[i:i+s]) for i in range(0, len(w), s - o)]"
    assert 0 < evaluate(q, buggy)["score"] < 1
    assert evaluate(q, "def chunk_text(t, s, o):\n    while True: pass")["score"] == 0
    assert "SyntaxError" in evaluate(q, "def chunk_text(t, s, o) return")["feedback"]


def test_rubric_rewards_substance_not_keyword_lists():
    q = BY_ID["rag-1"]
    good = evaluate(q, BY_ID["rag-1"]["model_answer"])["score"]
    keywords = evaluate(q, "chunk embed vector retrieve prompt generate")["score"]
    assert good >= 0.8 and keywords <= 0.4


def test_idk_gets_zero_and_reference():
    r = evaluate(BY_ID["llm-1"], "I don't know")
    assert r["score"] == 0 and r["reference"]


def test_llm_grader_used_and_clamped():
    r = evaluate(BY_ID["llm-1"], "tokens...", FakeLLM({"score": 1.7, "covered": [], "missed": [], "feedback": "f", "follow_up": ""}))
    assert r["score"] == 1.0 and r["grader"] == "fake:fake-1"


def test_role_match_prefers_first_choice_roles(profile):
    assert role_match("AI Engineer Intern, Agent Platform", profile["target_roles"]) > \
        role_match("Research Assistant, LLM evaluation", profile["target_roles"])


def test_fit_and_gaps(profile, memory):
    jd = {"title": "AI Engineer Intern", "type": "internship", "description": "LLM agents evaluation benchmark eval judge"}
    a = analyze(jd, profile, skill_levels(profile, memory))
    assert 0 <= a["fit"] <= 1 and a["gaps"][0][0] == "evaluation"


def test_full_session_interrupts_adapts_and_reports(profile, memory, offline, tmp_path):
    s = CoachSession(profile, memory, offline, max_questions=6, today="2026-11-01", session_id="t1", out_dir=tmp_path)
    asked = []
    state = s.run(lambda q: asked.append(q) or ANS1.get(q["qid"], "I don't know"))
    assert sum(not q["is_follow_up"] for q in asked) == 6
    assert any(q["is_follow_up"] for q in asked), "partial answers should trigger a follow-up challenge"
    assert any(q["kind"] == "coding" for q in asked) and any(q["kind"] == "behavioral" for q in asked)
    assert 0 < state["readiness"] < 1
    report = (tmp_path / "career_readiness_2026-11-01_t1.md").read_text()
    for section in ("Opportunities found", "Assessment results", "Knowledge gaps", "Recommended resources",
                    "14-day preparation plan", "Progress over time"):
        assert section in report


def test_progress_is_tracked_across_sessions(profile, memory, offline, tmp_path):
    CoachSession(profile, memory, offline, today="2026-11-01", session_id="a", out_dir=tmp_path).run(
        lambda q: ANS1.get(q["qid"], "I don't know"))
    s2 = CoachSession(profile, memory, offline, today="2026-11-08", session_id="b", out_dir=tmp_path).run(
        lambda q: ANS2.get(q["qid"], "I don't know"))
    hist = memory.sessions()
    assert [h["ts"] for h in hist] == ["2026-11-01", "2026-11-08"]
    assert hist[1]["readiness"] > hist[0]["readiness"]
    assert "Change since last session" in s2["report"]


def test_coach_results_feed_daily_brief(profile, memory, offline, tmp_path):
    """Shared memory: weak assessment on a topic raises its learning-gap weight for Agent 1."""
    before = skill_levels(profile, memory).get("mlops")
    memory.update_mastery("mlops", 0.0, prior=before)
    assert skill_levels(profile, memory)["mlops"] < before
