"""Find internships, jobs, research and entrepreneurial opportunities.

Live tools (public, no auth):
  Greenhouse job board API  https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
  Lever postings API        https://api.lever.co/v0/postings/{company}?mode=json
  arXiv API                 recent papers in your research interests -> research leads
Offline: data/fixtures/sample_jds.json (synthetic, clearly labeled) + profile entries.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..tech_upgrade.fetch import HEADERS, clean_html

ROLE_WORDS = re.compile(r"\b(intern|internship|co-?op|new grad|university|graduate|student|engineer|scientist|research)\b", re.I)
AI_WORDS = re.compile(r"\b(ai|ml|machine learning|llm|agent|applied|inference|research)\b", re.I)


def classify(title: str) -> str:
    t = title.lower()
    if "intern" in t or "co-op" in t:
        return "internship"
    if "research" in t and ("assistant" in t or "fellow" in t):
        return "research"
    return "job"


def _keep(title: str, location: str, locations: list[str]) -> bool:
    if not (ROLE_WORDS.search(title) and AI_WORDS.search(title)):
        return False
    if not locations:
        return True
    return any(l.lower() in (location or "").lower() for l in locations)


def fetch_greenhouse(token: str, locations: list[str], timeout: int = 20) -> list[dict]:
    import requests
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
    data = requests.get(url, params={"content": "true"}, headers=HEADERS, timeout=timeout).json()
    out = []
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name", "")
        if _keep(j.get("title", ""), loc, locations):
            out.append({"title": j["title"], "company": token, "location": loc, "url": j.get("absolute_url"),
                        "type": classify(j["title"]), "source": "Greenhouse",
                        "description": clean_html(j.get("content", ""))[:8000]})
    return out


def fetch_lever(company: str, locations: list[str], timeout: int = 20) -> list[dict]:
    import requests
    data = requests.get(f"https://api.lever.co/v0/postings/{company}", params={"mode": "json"},
                        headers=HEADERS, timeout=timeout).json()
    out = []
    for j in data if isinstance(data, list) else []:
        loc = (j.get("categories") or {}).get("location", "")
        if _keep(j.get("text", ""), loc, locations):
            desc = j.get("descriptionPlain", "") + " " + " ".join(
                clean_html(l.get("content", "")) for l in j.get("lists", []))
            out.append({"title": j["text"], "company": company, "location": loc, "url": j.get("hostedUrl"),
                        "type": classify(j["text"]), "source": "Lever", "description": desc[:8000]})
    return out


def research_leads(profile: dict, limit: int = 4) -> list[dict]:
    """Recent arXiv papers in your interests: read, reproduce, or contact authors/SJSU faculty."""
    from ..tech_upgrade.fetch import arxiv_query, fetch_arxiv
    src = {"name": "arXiv", "org": "arXiv", "url": "http://export.arxiv.org/api/query", "authority": 0.75}
    papers = fetch_arxiv(src, arxiv_query(profile), limit=limit)
    return [{"title": f"Research lead: reproduce or extend \"{p['title']}\"", "company": "arXiv", "location": "Remote",
             "url": p["url"], "type": "research", "source": "arXiv", "description": p["summary"]} for p in papers]


def entrepreneurship_leads(profile: dict) -> list[dict]:
    return [{"title": e["title"], "company": "Entrepreneurship", "location": "—", "url": e.get("url"),
             "type": "entrepreneurial", "source": "profile", "description": e.get("notes", "")}
            for e in profile.get("entrepreneurship", [])]


def load_sample_jds(path: str | Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["opportunities"]


def discover(profile: dict, sample_path: str | Path | None = None, live: bool = False) -> tuple[list[dict], list[str]]:
    opps, errors = [], []
    if sample_path:
        opps += load_sample_jds(sample_path)
    if live:
        locs = profile.get("job_locations", [])
        for token in profile.get("job_boards", {}).get("greenhouse", []):
            try:
                opps += fetch_greenhouse(token, locs)
            except Exception as e:
                errors.append(f"greenhouse:{token}: {type(e).__name__}")
        for company in profile.get("job_boards", {}).get("lever", []):
            try:
                opps += fetch_lever(company, locs)
            except Exception as e:
                errors.append(f"lever:{company}: {type(e).__name__}")
        try:
            opps += research_leads(profile)
        except Exception as e:
            errors.append(f"arxiv: {type(e).__name__}")
    opps += entrepreneurship_leads(profile)
    return opps, errors
