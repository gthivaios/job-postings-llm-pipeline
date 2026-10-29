"""Logic tests for sample validation and manifest, run on SQLite (no Docker needed)."""

import pytest
from sqlalchemy import create_engine, text

from jobpipe.sample import prepare

SCHEMA = """
CREATE TABLE `{t}` (
  `id` INTEGER NOT NULL, `title` TEXT NOT NULL, `url` TEXT NOT NULL, `location` TEXT,
  `posted` TEXT, `scraped` TIMESTAMP, `company` TEXT, `description` TEXT, `type` TEXT
)"""


@pytest.fixture
def conn():
    engine = create_engine("sqlite://")
    with engine.begin() as c:
        for t in ["jobseeker", "portal_b"]:
            c.execute(text(SCHEMA.format(t=t)))
        c.execute(text("CREATE TABLE notes (x TEXT)"))  # unrelated table, must be skipped
        rows = [
            (
                i,
                f"Λογιστής {i}",
                f"https://ex.gr/{i}",
                "Αθήνα",
                f"2025-11-{1 + i % 10:02d} 10:00",
                "Εταιρεία ΑΕ",
                "Μισθός 1200€. Βιογραφικά: hr@ex.gr, τηλ 210 123 4567"
                if i % 3 == 0
                else "Χωρίς στοιχεία επικοινωνίας",
            )
            for i in range(1, 2501)  # > one batch, to exercise keyset pagination
        ]
        c.execute(
            text(
                "INSERT INTO jobseeker (id,title,url,location,scraped,company,description) "
                "VALUES (:0,:1,:2,:3,:4,:5,:6)"
            ),
            [dict(zip(map(str, range(7)), r, strict=True)) for r in rows],
        )
        c.execute(
            text(
                "INSERT INTO portal_b (id,title,url,posted,scraped,description) VALUES "
                "(1,'Πωλητής','u','Πριν 3 ώρες','2025-11-03 09:00',NULL)"
            )
        )
        yield c


def test_manifest_counts_and_dates(conn):
    manifest = prepare(conn)

    assert manifest["tables"] == {"jobseeker": 2500, "portal_b": 1}
    assert manifest["total_rows"] == 2501
    assert (manifest["scraped_from"], manifest["scraped_to"]) == ("2025-11-01", "2025-11-10")


def test_data_left_unchanged(conn):
    before = conn.execute(text("SELECT * FROM jobseeker ORDER BY id")).all()
    prepare(conn)
    assert conn.execute(text("SELECT * FROM jobseeker ORDER BY id")).all() == before
    desc = conn.execute(text("SELECT description FROM jobseeker WHERE id = 3")).scalar_one()
    assert desc == "Μισθός 1200€. Βιογραφικά: hr@ex.gr, τηλ 210 123 4567"


def test_prepare_is_repeatable(conn):
    assert prepare(conn) == prepare(conn)


def test_duplicate_ids_rejected(conn):
    conn.execute(
        text("INSERT INTO portal_b (id,title,url,posted) VALUES (1,'dup','u','2025-11-04')")
    )
    with pytest.raises(ValueError, match="duplicate ids"):
        prepare(conn)
