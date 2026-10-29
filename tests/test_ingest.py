"""Ingest stage tests on SQLite: analysis DB as main, raw DB attached as `raw_portals`.

Runs the real Alembic migration and the real INSERT ... SELECT, so no Docker needed.
"""

import hashlib

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, event, text

from jobpipe.db.schema import metadata
from jobpipe.ingest import ingest, make_uid

RAW_SCHEMA = """
CREATE TABLE raw_portals.`{t}` (
  `id` INTEGER NOT NULL, `title` TEXT NOT NULL, `url` TEXT NOT NULL, `location` TEXT,
  `posted` TEXT, `scraped` TIMESTAMP, `company` TEXT, `description` TEXT, `type` TEXT
)"""


@pytest.fixture
def engine(tmp_path):
    analysis, raw = tmp_path / "analysis.db", tmp_path / "raw.db"
    eng = create_engine(f"sqlite:///{analysis}")

    @event.listens_for(eng, "connect")
    def _setup(dbapi_conn, _):
        dbapi_conn.execute(f"ATTACH DATABASE '{raw}' AS raw_portals")
        dbapi_conn.create_function(  # MariaDB's SHA2(str, 256)
            "SHA2", 2, lambda s, _bits: hashlib.sha256(str(s).encode()).hexdigest()
        )

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{analysis}")
    command.upgrade(cfg, "head")

    with eng.begin() as c:
        for t in ["jobseeker", "kariera", "xe"]:
            c.execute(text(RAW_SCHEMA.format(t=t)))
        c.execute(text("CREATE TABLE raw_portals.notes (x TEXT)"))  # not a portal table
        # Same source id 1 in two portals: must become two distinct postings
        c.execute(
            text(
                "INSERT INTO raw_portals.jobseeker (id,title,url,posted,scraped,type) VALUES "
                "(1,'Λογιστής','u1','Πριν 3 ώρες','2025-11-01 10:00','Πλήρης'),"
                "(2,'Πωλητής','u2','2025-11-02','2025-11-02 08:00',NULL)"
            )
        )
        c.execute(
            text(
                "INSERT INTO raw_portals.kariera (id,title,url,company) "
                "VALUES (1,'Οδηγός','u3','ΑΕ')"
            )
        )
    return eng


def test_migration_matches_schema(engine):
    with engine.connect() as c:
        diff = compare_metadata(MigrationContext.configure(c), metadata)
    assert diff == [], f"schema.py and migrations differ: {diff}"


def test_ingest_unifies_with_portal_and_uid(engine):
    with engine.begin() as c:
        assert ingest(c, "raw_portals") == {"jobseeker": 2, "kariera": 1, "xe": 0}
        rows = c.execute(
            text(
                "SELECT uid, portal, source_id, title, job_type, posted "
                "FROM unified_postings ORDER BY uid"
            )
        ).all()

    assert {(r.portal, r.source_id) for r in rows} == {
        ("jobseeker", 1),
        ("jobseeker", 2),
        ("kariera", 1),
    }
    assert len({r.uid for r in rows}) == 3
    by_key = {(r.portal, r.source_id): r for r in rows}
    assert by_key[("jobseeker", 1)].job_type == "Πλήρης"
    assert by_key[("jobseeker", 1)].posted == "Πριν 3 ώρες"  # free text kept as published
    assert by_key[("kariera", 1)].title == "Οδηγός"


def test_sql_uid_matches_python(engine):
    with engine.begin() as c:
        ingest(c, "raw_portals")
        rows = c.execute(text("SELECT uid, portal, source_id FROM unified_postings")).all()
    for r in rows:
        assert r.uid == make_uid(r.portal, r.source_id)


def test_ingest_is_idempotent(engine):
    with engine.begin() as c:
        ingest(c, "raw_portals")
        assert ingest(c, "raw_portals") == {"jobseeker": 0, "kariera": 0, "xe": 0}
        assert c.execute(text("SELECT COUNT(*) FROM unified_postings")).scalar_one() == 3


def test_ingest_picks_up_new_rows_only(engine):
    with engine.begin() as c:
        ingest(c, "raw_portals")
        c.execute(text("INSERT INTO raw_portals.xe (id,title,url) VALUES (9,'Μάγειρας','u9')"))
        assert ingest(c, "raw_portals") == {"jobseeker": 0, "kariera": 0, "xe": 1}


def test_uid_is_stable():
    # Pinned value: if this changes, every downstream reference (eval sets, traces) breaks
    assert make_uid("jobseeker", 1) == hashlib.sha256(b"jobseeker:1").hexdigest()[:16]
    assert len(make_uid("jobseeker", 1)) == 16
