"""Checks that the sample DB built by `docker compose up -d db` matches the manifest.

Run with:  uv run pytest -m db
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from jobpipe.config import Settings

pytestmark = pytest.mark.db

MANIFEST = Path(__file__).parents[1] / "data" / "sample_manifest.json"


@pytest.fixture(scope="module")
def manifest():
    if not MANIFEST.exists():
        pytest.skip("data/sample_manifest.json not created yet")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def conn():
    s = Settings()
    engine = create_engine(s.url(s.raw_db))
    with engine.connect() as c:
        yield c


def test_row_counts_match_manifest(conn, manifest):
    for table, expected in manifest["tables"].items():
        got = conn.execute(text(f"SELECT COUNT(*) FROM `{table}`")).scalar_one()
        assert got == expected, f"{table}: expected {expected}, got {got}"


def test_greek_text_round_trips(conn, manifest):
    table = next(iter(manifest["tables"]))
    sample = conn.execute(
        text(f"SELECT title FROM `{table}` WHERE title REGEXP '[α-ωΑ-Ω]' LIMIT 1")
    ).scalar()
    assert sample, "no Greek text found; check utf8mb4 settings"
    assert "Ã" not in sample and "?" * 3 not in sample
