"""The raw portal tables: one table per portal, all with the same structure."""

import logging

from sqlalchemy import Connection, inspect

log = logging.getLogger(__name__)

KEY_COLUMN = "id"
# `posted` is free text on some portals ("Πριν 3 ώρες"), so `scraped` is the date we use
DATE_COLUMN = "scraped"
TEXT_COLUMNS = ["title", "description", "company"]
COLUMNS = ["id", "title", "url", "location", "posted", "scraped", "company", "description", "type"]


def portal_tables(conn: Connection, schema: str | None = None) -> list[str]:
    """Names of every table with the portal structure. The table name is the portal name."""
    insp = inspect(conn)
    tables = []
    for name in sorted(insp.get_table_names(schema=schema)):
        cols = {c["name"] for c in insp.get_columns(name, schema=schema)}
        if set(COLUMNS) <= cols:
            tables.append(name)
        else:
            log.warning("skipping %s: not a portal table", name)
    return tables
