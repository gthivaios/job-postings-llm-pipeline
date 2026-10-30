"""Translation stage tests: real migrations and SQL on SQLite, fake LLM (no API key, no cost)."""

import threading
from datetime import date, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, insert, select, text

from jobpipe.config import Settings
from jobpipe.db.schema import llm_cache, unified_postings
from jobpipe.llm import LLMResult
from jobpipe.translate import clean_translation, run

DAY = date(2026, 4, 1)


class FakeLLM:
    """Echoes 'EN<text>' and records every call. Fails on texts containing a marker."""

    def __init__(self, model="fake/model", fail_marker=None):
        self.model = model
        self.fail_marker = fail_marker
        self.calls: list[str] = []
        self._lock = threading.Lock()

    def complete(self, system: str, user: str) -> LLMResult:
        with self._lock:
            self.calls.append(user)
        if self.fail_marker and self.fail_marker in user:
            raise RuntimeError("provider error")
        return LLMResult(
            text=f"EN<{user}>",
            model=self.model,
            latency_ms=100,
            cost_usd=0.001,
            prompt_tokens=10,
            completion_tokens=10,
        )


def posting(uid, title, description=None, job_type=None, scraped="2026-04-01 10:00:00", **kw):
    return {
        "uid": uid,
        "portal": kw.get("portal", "kariera"),
        "source_id": int(uid, 16) % 100000,
        "title": title,
        "url": f"u/{uid}",
        "description": description,
        "job_type": job_type,
        "scraped": datetime.fromisoformat(scraped),
    }


@pytest.fixture
def settings():
    return Settings(chunk_max_words=4, chunk_max_chars=1000, unicode_form="NFC", _env_file=None)


@pytest.fixture
def engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'analysis.db'}"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    eng = create_engine(url)
    with eng.begin() as c:
        c.execute(
            insert(unified_postings),
            [
                posting("a1", "Λογιστής", "ένα δύο τρία τέσσερα πέντε έξι", "Πλήρης"),
                posting("a2", "Πωλητής 🚀", "Δείτε https://ex.gr/x εδώ", "Πλήρης"),
                posting("a3", "Οδηγός", None, None),
                posting("b1", "Άλλη μέρα", "κείμενο", None, scraped="2026-04-02 09:00:00"),
            ],
        )
    return eng


def rows(engine):
    with engine.connect() as c:
        return {r.uid: r for r in c.execute(select(unified_postings))}


def test_translates_only_the_selected_day(engine, settings):
    stats = run(engine.begin, FakeLLM(), settings, DAY)
    r = rows(engine)
    assert stats.postings_done == 3
    assert {u for u, x in r.items() if x.en_description} == {"a1", "a2", "a3"}
    assert r["b1"].en_description is None


def test_en_description_is_title_type_and_chunked_body(engine, settings):
    run(engine.begin, FakeLLM(), settings, DAY)
    a1 = rows(engine)["a1"]
    assert a1.en_title == "EN<Λογιστής>"
    assert a1.en_job_type == "EN<Πλήρης>"
    # 6 words with max_words=4 -> two chunks, translated separately and joined
    body = "EN<ένα δύο τρία τέσσερα> EN<πέντε έξι>"
    assert a1.en_description == f"EN<Λογιστής>\n\nEN<Πλήρης>\n\n{body}"
    assert a1.translation_model == "fake/model"


def test_text_is_normalised_before_translation(engine, settings):
    llm = FakeLLM()
    run(engine.begin, llm, settings, DAY)
    assert "Πωλητής" in llm.calls  # emoji removed
    assert "Δείτε εδώ" in llm.calls  # URL removed
    assert not any("http" in c or "🚀" in c for c in llm.calls)


def test_missing_fields_are_skipped(engine, settings):
    run(engine.begin, FakeLLM(), settings, DAY)
    a3 = rows(engine)["a3"]
    assert a3.en_description == "EN<Οδηγός>"
    assert a3.en_job_type is None


def test_shared_text_is_translated_once_and_charged_once(engine, settings):
    llm = FakeLLM()
    stats = run(engine.begin, llm, settings, DAY)
    assert llm.calls.count("Πλήρης") == 1  # used by a1 and a2
    # 7 distinct texts: 3 titles, 1 shared type, 3 description chunks
    assert stats.llm_calls == len(llm.calls) == 7
    r = rows(engine)
    total = sum(x.translation_cost_usd or 0 for x in r.values())
    assert total == pytest.approx(stats.cost_usd) == pytest.approx(0.007)


def test_rerun_does_nothing_and_cache_is_filled(engine, settings):
    run(engine.begin, FakeLLM(), settings, DAY)
    llm = FakeLLM()
    stats = run(engine.begin, llm, settings, DAY)
    assert llm.calls == [] and stats.postings_done == 0
    with engine.connect() as c:
        assert c.execute(select(llm_cache)).all()


def test_cache_is_reused_for_new_postings(engine, settings):
    run(engine.begin, FakeLLM(), settings, DAY)
    with engine.begin() as c:
        c.execute(insert(unified_postings), [posting("a4", "Λογιστής", None, "Πλήρης")])
    llm = FakeLLM()
    stats = run(engine.begin, llm, settings, DAY)
    assert llm.calls == [] and stats.cache_hits == 2 and stats.postings_done == 1
    assert rows(engine)["a4"].translation_cost_usd == 0


def test_cache_is_per_model(engine, settings):
    run(engine.begin, FakeLLM(model="m1"), settings, DAY, limit=1)
    with engine.begin() as c:
        c.execute(text("UPDATE unified_postings SET en_description = NULL"))
    llm = FakeLLM(model="m2")
    run(engine.begin, llm, settings, DAY, limit=1)
    assert llm.calls  # m1's cache entries are not used for m2


def test_failed_posting_stays_null_and_is_retried(engine, settings):
    stats = run(engine.begin, FakeLLM(fail_marker="Οδηγός"), settings, DAY)
    assert stats.postings_failed == 1 and stats.postings_done == 2
    assert rows(engine)["a3"].en_description is None

    llm = FakeLLM()
    stats = run(engine.begin, llm, settings, DAY)
    assert stats.postings_done == 1 and llm.calls == ["Οδηγός"]


def test_portal_and_limit_filters(engine, settings):
    with engine.begin() as c:
        c.execute(insert(unified_postings), [posting("c1", "Μάγειρας", portal="xe")])
    stats = run(engine.begin, FakeLLM(), settings, DAY, portal="xe")
    assert stats.postings_done == 1 and rows(engine)["c1"].en_description
    stats = run(engine.begin, FakeLLM(), settings, DAY, limit=2)
    assert stats.postings_done == 2


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("Accountant", "Accountant"),
        ("Translation: Accountant", "Accountant"),
        ('"Accountant"', "Accountant"),
        ("English translation: «Sales clerk»", "Sales clerk"),
        ("  Driver \n", "Driver"),
    ],
)
def test_clean_translation(raw, clean):
    assert clean_translation(raw) == clean
