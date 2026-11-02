"""Discovery tools: RSS feeds, HTML index pages, arXiv API, offline snapshots."""
from __future__ import annotations

import html
import json
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

HEADERS = {"User-Agent": "SJSU-DailyTechUpgradeAgent/1.0 (student project; respectful polling)"}


def clean_html(text: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text or "", flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _iso(dt_struct=None, raw: str | None = None) -> str | None:
    try:
        if dt_struct:
            return datetime(*dt_struct[:6], tzinfo=timezone.utc).date().isoformat()
        if raw:
            try:
                return parsedate_to_datetime(raw).date().isoformat()
            except (TypeError, ValueError):
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        return None
    return None


def _article(source: dict, title: str, url: str, published: str | None, summary: str) -> dict:
    return {"title": clean_html(title), "url": url, "source": source["name"], "org": source["org"],
            "published": published, "summary": clean_html(summary)[:2500], "authority": source["authority"]}


def fetch_rss(source: dict, limit: int = 15, timeout: int = 15) -> list[dict]:
    import feedparser
    import requests
    resp = requests.get(source["url"], headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    out = []
    for e in feed.entries[:limit]:
        summary = e.get("summary", "") or (e.get("content") or [{}])[0].get("value", "")
        published = _iso(e.get("published_parsed") or e.get("updated_parsed"), e.get("published"))
        out.append(_article(source, e.get("title", ""), e.get("link", ""), published, summary))
    return out


def fetch_html_index(source: dict, limit: int = 12, timeout: int = 15) -> list[dict]:
    """For sources without RSS: collect article links from the index page.
    Dates/summaries are filled in later by fetch_article_text when an LLM is available."""
    import requests
    resp = requests.get(source["url"], headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    base = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(source["url"]))
    prefix = source.get("link_prefix", "/")
    seen, out = set(), []
    for href, inner in re.findall(r'<a[^>]+href="([^"#?]+)"[^>]*>(.*?)</a>', resp.text, flags=re.S):
        if not href.startswith(prefix) or href.rstrip("/") == prefix.rstrip("/"):
            continue
        url = urllib.parse.urljoin(base, href)
        title = clean_html(inner)
        if url in seen or len(title) < 12:
            continue
        seen.add(url)
        out.append(_article(source, title[:200], url, None, ""))
        if len(out) >= limit:
            break
    return out


def fetch_arxiv(source: dict, query: str, limit: int = 10, timeout: int = 20) -> list[dict]:
    import feedparser
    import requests
    params = {"search_query": query, "sortBy": "submittedDate", "sortOrder": "descending", "max_results": limit}
    resp = requests.get(source["url"], params=params, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    return [_article(source, e.title, e.link, _iso(e.get("published_parsed")), e.get("summary", ""))
            for e in feed.entries]


def arxiv_query(profile: dict) -> str:
    terms = profile.get("research_interests") or ["LLM agents"]
    q = " OR ".join(f'all:"{t}"' for t in terms[:3])
    return f"({q}) AND (cat:cs.AI OR cat:cs.CL OR cat:cs.LG)"


def fetch_all(sources: list[dict], profile: dict, per_source: int = 12, workers: int = 8):
    """Fetch every source concurrently. Returns (articles, errors). A failing feed never fails the run."""
    def one(src):
        if src["kind"] == "rss":
            return fetch_rss(src, per_source)
        if src["kind"] == "html":
            return fetch_html_index(src, per_source)
        if src["kind"] == "arxiv":
            return fetch_arxiv(src, arxiv_query(profile), per_source)
        return []

    articles, errors = [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, s): s for s in sources}
        for fut, src in futures.items():
            try:
                articles.extend(fut.result())
            except Exception as exc:  # network, 403, parse errors
                errors.append(f"{src['name']}: {type(exc).__name__}: {str(exc)[:120]}")
    return articles, errors


def fetch_article_text(url: str, max_chars: int = 12000, timeout: int = 15) -> str:
    """Best-effort full text for richer LLM summaries."""
    try:
        import requests
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        body = re.search(r"<(article|main)[^>]*>(.*?)</\1>", resp.text, flags=re.S | re.I)
        return clean_html(body.group(2) if body else resp.text)[:max_chars]
    except Exception:
        return ""


def load_snapshot(path: str | Path) -> list[dict]:
    """Offline mode: a JSON list of articles captured earlier (same schema as fetchers)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["articles"] if isinstance(data, dict) else data
