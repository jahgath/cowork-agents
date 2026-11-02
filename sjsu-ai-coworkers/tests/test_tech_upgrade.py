from datetime import date

from conftest import SNAPSHOT, FakeLLM
from coworkers.tech_upgrade.brief import plan_session
from coworkers.tech_upgrade.graph import run_daily_brief
from coworkers.tech_upgrade.scoring import score_article, select_diverse
from coworkers.tech_upgrade.summarize import make_card


def test_brief_has_three_diverse_articles_with_required_fields(profile, memory, offline, tmp_path):
    res = run_daily_brief(profile, memory, offline, date="2026-11-01", snapshot=str(SNAPSHOT), out_dir=tmp_path)
    cards = res["cards"]
    assert len(cards) == 3
    assert len({c["org"] for c in cards}) == 3, "picks should come from different organizations"
    for c in cards:
        for field in ("title", "url", "source", "published", "summary", "key_insights", "why_it_matters", "career_link"):
            assert field in c
    md = res["markdown"]
    assert md.count("URL: https://") == 3 and "Reading plan" in md
    assert (tmp_path / "daily_brief_2026-11-01.md").exists()


def test_recent_substantive_article_ranks_first(profile, memory, offline, tmp_path):
    res = run_daily_brief(profile, memory, offline, date="2026-11-01", snapshot=str(SNAPSHOT), out_dir=tmp_path)
    assert res["cards"][0]["title"] == "Redesigning source control at Anthropic"


def test_seen_articles_are_not_repeated_next_day(profile, memory, offline, tmp_path):
    day1 = run_daily_brief(profile, memory, offline, date="2026-11-01", snapshot=str(SNAPSHOT), out_dir=tmp_path)
    day2 = run_daily_brief(profile, memory, offline, date="2026-11-02", snapshot=str(SNAPSHOT), out_dir=tmp_path)
    assert not {c["url"] for c in day1["cards"]} & {c["url"] for c in day2["cards"]}


def test_ratings_change_interest_and_ranking(profile, memory):
    art = {"title": "Evaluating LLM agents with LLM-as-a-judge", "url": "u", "org": "X", "source": "X",
           "summary": "evaluation benchmark judge metrics " * 20, "authority": 0.8, "published": "2026-10-30"}
    memory.record_recommendations("2026-11-01", [{**art, "primary_topic": "evaluation", "score": 0.5}])
    from coworkers.profile import effective_interests
    before = score_article(art, effective_interests(profile, memory), {}, {}, date(2026, 11, 1))["score"]
    memory.rate("u", 1)
    after = score_article(art, effective_interests(profile, memory), {}, {}, date(2026, 11, 1))["score"]
    assert after < before


def test_thin_teaser_is_discounted(profile):
    base = {"url": "a", "org": "X", "source": "X", "authority": 0.8, "published": "2026-10-30"}
    thin = score_article({**base, "title": "Agents", "summary": "An agent post."}, profile["interests"], {}, {}, date(2026, 11, 1))
    rich = score_article({**base, "title": "Agents", "summary": "An agent post about orchestration. " * 30},
                         profile["interests"], {}, {}, date(2026, 11, 1))
    assert thin["depth"] < rich["depth"] and thin["score"] < rich["score"]


def test_diversity_penalty_spreads_sources():
    arts = [{"url": str(i), "org": "A" if i < 3 else "B", "primary_topic": "agents", "score": 1 - i * 0.01} for i in range(5)]
    picks = select_diverse(arts, 3)
    assert {"A", "B"} <= {p["org"] for p in picks}


def test_session_fits_15_to_20_minutes():
    for mins in ([6, 6, 6], [15, 15, 15], [3, 3, 3], [12, 4, 5]):
        alloc = plan_session([{"reading_minutes": m} for m in mins], 18)
        assert 15 <= sum(alloc) + 2 <= 20


def test_llm_card_path_used_when_available(profile):
    fake = FakeLLM({"summary": "S", "key_insights": ["a", "b", "c"], "takeaways": ["x", "y"], "why_it_matters": "w",
                    "career_link": "c", "quiz_question": "q", "difficulty": "advanced"})
    card = make_card({"title": "T", "url": "u", "source": "s", "summary": "text", "topics": {"agents": 1}}, profile, fake)
    assert card["generated_by"] == "fake:fake-1" and card["difficulty"] == "advanced" and fake.calls == 1


def test_llm_failure_falls_back_to_offline(profile):
    card = make_card({"title": "T", "url": "u", "source": "s", "summary": "Agents call tools in a loop. It works.",
                      "topics": {"agents": 1}, "primary_topic": "agents"}, profile, FakeLLM(None))
    assert card["generated_by"] == "offline-extractive"
