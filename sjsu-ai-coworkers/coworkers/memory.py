"""Long-term memory shared by both coworkers (SQLite, zero setup).

Short-term / per-run memory lives in each LangGraph state + checkpointer.
This module is the *long-term* memory:

  recommendations   every article Agent 1 has recommended (+ rating, read flag)
  interest_adjust   learned interest deltas from article ratings
  topic_progress    exposure (reading) and mastery (assessment) per topic
  assessments       every question Agent 2 asked, the answer, score, feedback
  sessions          coaching sessions with overall readiness, for trend tracking
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .taxonomy import primary_topic

SCHEMA = """
CREATE TABLE IF NOT EXISTS recommendations (
    url TEXT PRIMARY KEY, title TEXT, source TEXT, topic TEXT, published TEXT,
    recommended_on TEXT, score REAL, rating INTEGER, read INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS interest_adjust (topic TEXT PRIMARY KEY, delta REAL);
CREATE TABLE IF NOT EXISTS topic_progress (
    topic TEXT PRIMARY KEY, exposure REAL DEFAULT 0, mastery REAL, attempts INTEGER DEFAULT 0,
    updated TEXT);
CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, ts TEXT, topic TEXT, kind TEXT,
    difficulty INTEGER, question TEXT, answer TEXT, score REAL, feedback TEXT);
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY, ts TEXT, target TEXT, readiness REAL, assessment_score REAL,
    fit REAL, topic_scores TEXT, report_path TEXT);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Memory:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---------------- Agent 1: recommendations & feedback ----------------
    def seen_urls(self) -> set[str]:
        return {r["url"] for r in self.conn.execute("SELECT url FROM recommendations")}

    def record_recommendations(self, date: str, items: list[dict]) -> None:
        for it in items:
            self.conn.execute(
                "INSERT OR REPLACE INTO recommendations(url,title,source,topic,published,recommended_on,score)"
                " VALUES (?,?,?,?,?,?,?)",
                (it["url"], it["title"], it["source"], it.get("primary_topic"), it.get("published"),
                 date, it.get("score")))
            # recommending = small exposure bump; actually reading adds more (mark_read)
            if it.get("primary_topic"):
                self.add_exposure(it["primary_topic"], 0.25)
        self.conn.commit()

    def rate(self, url: str, rating: int) -> str | None:
        """1-5 rating. Ratings nudge topic interest up (4-5) or down (1-2)."""
        row = self.conn.execute("SELECT topic, title FROM recommendations WHERE url=?", (url,)).fetchone()
        if not row:
            return None
        self.conn.execute("UPDATE recommendations SET rating=? WHERE url=?", (rating, url))
        topic = row["topic"] or primary_topic(row["title"])
        if topic:
            delta = {1: -0.15, 2: -0.08, 3: 0.0, 4: 0.06, 5: 0.12}[int(rating)]
            cur = self.interest_adjustments().get(topic, 0.0)
            self.conn.execute("INSERT OR REPLACE INTO interest_adjust(topic,delta) VALUES (?,?)",
                              (topic, max(-0.6, min(0.6, cur + delta))))
        self.conn.commit()
        return topic

    def mark_read(self, url: str) -> None:
        row = self.conn.execute("SELECT topic FROM recommendations WHERE url=?", (url,)).fetchone()
        self.conn.execute("UPDATE recommendations SET read=1 WHERE url=?", (url,))
        if row and row["topic"]:
            self.add_exposure(row["topic"], 1.0)
        self.conn.commit()

    def interest_adjustments(self) -> dict[str, float]:
        return {r["topic"]: r["delta"] for r in self.conn.execute("SELECT * FROM interest_adjust")}

    def recommendation_history(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM recommendations ORDER BY recommended_on DESC, score DESC")]

    # ---------------- shared: topic progress ----------------
    def add_exposure(self, topic: str, amount: float) -> None:
        self.conn.execute(
            "INSERT INTO topic_progress(topic,exposure,updated) VALUES (?,?,?) "
            "ON CONFLICT(topic) DO UPDATE SET exposure=exposure+excluded.exposure, updated=excluded.updated",
            (topic, amount, _now()))
        self.conn.commit()

    def update_mastery(self, topic: str, score: float, prior: float | None = None, alpha: float = 0.5) -> float:
        """Exponential moving average of assessment scores (0..1). The first observation is blended
        with the prior (self-rating) so one lucky answer doesn't read as full mastery."""
        row = self.conn.execute("SELECT mastery, attempts FROM topic_progress WHERE topic=?", (topic,)).fetchone()
        old = row["mastery"] if row and row["mastery"] is not None else prior
        new = score if old is None else (1 - alpha) * old + alpha * score
        attempts = (row["attempts"] if row else 0) + 1
        self.conn.execute(
            "INSERT INTO topic_progress(topic,mastery,attempts,updated) VALUES (?,?,?,?) "
            "ON CONFLICT(topic) DO UPDATE SET mastery=excluded.mastery, attempts=excluded.attempts,"
            " updated=excluded.updated", (topic, new, attempts, _now()))
        self.conn.commit()
        return new

    def topic_mastery(self) -> dict[str, float]:
        return {r["topic"]: r["mastery"] for r in self.conn.execute(
            "SELECT topic, mastery FROM topic_progress WHERE mastery IS NOT NULL")}

    def topic_exposure(self) -> dict[str, float]:
        return {r["topic"]: r["exposure"] for r in self.conn.execute("SELECT topic, exposure FROM topic_progress")}

    # ---------------- Agent 2: assessments & sessions ----------------
    def save_assessment(self, session_id: str, item: dict) -> None:
        self.conn.execute(
            "INSERT INTO assessments(session_id,ts,topic,kind,difficulty,question,answer,score,feedback)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (session_id, _now(), item["topic"], item["kind"], item["difficulty"], item["question"],
             item["answer"], item["score"], item["feedback"]))
        self.conn.commit()

    def save_session(self, session_id: str, target: str, readiness: float, assessment_score: float,
                     fit: float, topic_scores: dict, report_path: str = "", ts: str | None = None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?)",
            (session_id, ts or _now(), target, readiness, assessment_score, fit, json.dumps(topic_scores), report_path))
        self.conn.commit()

    def sessions(self) -> list[dict]:
        rows = [dict(r) for r in self.conn.execute("SELECT * FROM sessions ORDER BY ts, session_id")]
        for r in rows:
            r["topic_scores"] = json.loads(r["topic_scores"] or "{}")
        return rows

    def asked_question_ids(self) -> set[str]:
        # question text is stored; ids are embedded as "[id] prompt"
        ids = set()
        for r in self.conn.execute("SELECT question FROM assessments"):
            q = r["question"] or ""
            if q.startswith("[") and "]" in q:
                ids.add(q[1:q.index("]")])
        return ids
