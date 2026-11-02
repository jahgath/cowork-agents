"""Evaluate a candidate's answer.

coding      -> extract code, run it against the question's unit tests in a
               subprocess with a timeout. Score = fraction of tests passed.
concept /
design /
behavioral  -> LLM rubric grading when a key is configured; otherwise rubric
               coverage: each key point is covered if any accepted phrasing
               appears. Very short answers are capped (no credit for keyword
               lists without explanation).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

from ..llm import LLM
from .question_bank import point_labels

IDK = re.compile(r"^\s*(i\s*(do\s*not|don'?t)\s*know|no idea|not sure|skip|pass)\b", re.I)

HARNESS = """
import json, copy, sys
__T = json.loads({tests!r})
__out = []
{code}

for __t in __T:
    try:
        __r = {func}(*copy.deepcopy(__t["args"]))
        __ok = json.loads(json.dumps(__r)) == __t["expected"]
        __out.append({{"ok": __ok, "got": json.loads(json.dumps(__r, default=str)), "expected": __t["expected"], "args": __t["args"]}})
    except Exception as __e:
        __out.append({{"ok": False, "error": type(__e).__name__ + ": " + str(__e)[:200], "args": __t["args"]}})
print("__RESULTS__" + json.dumps(__out))
"""


def extract_code(answer: str) -> str:
    m = re.findall(r"```(?:python|py)?\s*\n(.*?)```", answer or "", flags=re.S)
    return "\n".join(m) if m else (answer or "")


def run_code_tests(code: str, func_name: str, tests: list[dict], timeout: int = 5) -> dict:
    """Execute the candidate's code against tests in a separate Python process.
    NOTE: this runs your own code locally; it is a timeout-bounded subprocess, not a security sandbox."""
    script = HARNESS.format(tests=json.dumps(tests), code=textwrap.dedent(code), func=func_name)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "candidate.py"
        path.write_text(script, encoding="utf-8")
        try:
            proc = subprocess.run([sys.executable, "-I", str(path)], capture_output=True, text=True,
                                  timeout=timeout, cwd=tmp)
        except subprocess.TimeoutExpired:
            return {"passed": 0, "total": len(tests), "results": [], "error": f"Timed out after {timeout}s (infinite loop?)"}
    marker = proc.stdout.rfind("__RESULTS__")
    if marker == -1:
        err = (proc.stderr or "no output").strip().splitlines()
        return {"passed": 0, "total": len(tests), "results": [], "error": err[-1] if err else "unknown error"}
    results = json.loads(proc.stdout[marker + len("__RESULTS__"):].strip())
    return {"passed": sum(r["ok"] for r in results), "total": len(tests), "results": results, "error": None}


def _covered(point: list[str], text: str) -> bool:
    return any(p.lower() in text for p in point)


def rubric_grade(question: dict, answer: str) -> dict:
    text = " " + (answer or "").lower() + " "
    points = question.get("key_points", [])
    hits = [_covered(p, text) for p in points]
    coverage = sum(hits) / len(points) if points else 0.0
    words = len((answer or "").split())
    score = coverage
    notes = []
    if words < 20:
        score = min(score, 0.4)
        notes.append("Answer is very short; interviewers expect reasoning, not keywords.")
    elif words > 60 and coverage >= 0.5:
        score = min(1.0, score + 0.05)  # small credit for a developed explanation
    names = point_labels(question)
    covered = [n for n, h in zip(names, hits) if h]
    missed = [n for n, h in zip(names, hits) if not h]
    return {"score": round(score, 3), "covered": covered, "missed": missed, "notes": notes, "grader": "rubric"}


def llm_grade(question: dict, answer: str, llm: LLM) -> dict | None:
    system = ("You are a rigorous but encouraging technical interviewer. Grade strictly against the rubric. "
              "Do not reward confident wording without substance.")
    prompt = f"""Question ({question['kind']}, difficulty {question['difficulty']}/3): {question['prompt']}
Rubric key points (a point counts if the idea is clearly present, in any wording): {json.dumps(point_labels(question))}
Reference answer: {question.get('model_answer', '')}
Candidate answer:
<<<
{answer}
>>>
Return JSON: {{"score": float 0..1, "covered": [rubric points covered], "missed": [rubric points missed],
"feedback": "2-3 sentences: what was good, what was missing, how to improve",
"follow_up": "one probing follow-up question targeting the biggest gap, or empty string"}}"""
    data = llm.complete_json(system, prompt)
    if not data or "score" not in data:
        return None
    data["score"] = max(0.0, min(1.0, float(data["score"])))
    data["grader"] = llm.describe()
    return data


def evaluate(question: dict, answer: str, llm: LLM | None = None) -> dict:
    answer = answer or ""
    if not answer.strip() or IDK.match(answer):
        return {"score": 0.0, "covered": [], "missed": point_labels(question),
                "feedback": ("No worries — not knowing is useful signal. Study the reference answer below, then try explaining it back in your own words."
                             if question.get("model_answer") else
                             "No worries — not knowing is useful signal. This gap is now in your study plan; the resources in your report cover it."),
                "grader": "rule", "reference": question.get("model_answer", "")}

    if question["kind"] == "coding":
        res = run_code_tests(extract_code(answer), question["func_name"], question["tests"])
        score = res["passed"] / res["total"] if res["total"] else 0.0
        if res["error"]:
            fb = f"Your code didn't run: {res['error']}."
        elif score == 1:
            fb = f"All {res['total']} tests passed."
        else:
            fail = next(r for r in res["results"] if not r["ok"])
            detail = fail.get("error") or f"got {fail.get('got')!r}, expected {fail.get('expected')!r}"
            fb = f"{res['passed']}/{res['total']} tests passed. First failure on input {fail['args']!r}: {detail}."
        return {"score": round(score, 3), "covered": [], "missed": [], "feedback": fb, "grader": "unit-tests",
                "tests": res, "reference": question.get("model_answer", "")}

    graded = llm_grade(question, answer, llm) if (llm and llm.available) else None
    if graded is None:
        graded = rubric_grade(question, answer)
        parts = []
        if graded["covered"]:
            parts.append("Covered: " + "; ".join(graded["covered"]) + ".")
        if graded["missed"]:
            parts.append("Missing: " + "; ".join(graded["missed"]) + ".")
        parts += graded.pop("notes")
        graded["feedback"] = " ".join(parts)
    graded["reference"] = question.get("model_answer", "")
    return graded
