"""Checks the ingest stage against the real MariaDB sample.

Run after:  uv run alembic upgrade head && uv run python -m jobpipe.ingest
Then:       uv run pytest -m db
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from jobpipe.config import Settings
from jobpipe.ingest import make_uid

pytestmark = pytest.mark.db

MANIFEST = Path(__file__).parents[1] / "data" / "sample_manifest.json"


@pytest.fixture(scope="module")
def conn():
    if not MANIFEST.exists():
        pytest.skip("data/sample_manifest.json not created yet")
    s = Settings()
    with create_engine(s.url(s.analysis_db)).connect() as c:
        yield c


def test_every_raw_row_ingested_once(conn):
    expected = json.loads(MANIFEST.read_text(encoding="utf-8"))["tables"]
    got = dict(
        conn.execute(text("SELECT portal, COUNT(*) FROM unified_postings GROUP BY portal")).all()
    )
    assert got == expected


def test_mariadb_uid_matches_python(conn):
    rows = conn.execute(text("SELECT uid, portal, source_id FROM unified_postings LIMIT 100")).all()
    assert rows
    for r in rows:
        assert r.uid == make_uid(r.portal, r.source_id)
