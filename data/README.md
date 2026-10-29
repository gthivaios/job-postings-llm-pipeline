# Sample data card

| Field | Value |
|---|---|
| Source | 6 Greek job portals (public listings) |
| Period | see `scraped_from` / `scraped_to` in `sample_manifest.json` (10 days) |
| Tables | `raw_portals.*`, one per portal, identical structure |
| Rows | see `sample_manifest.json` |
| Language | Greek (some English) |

## Columns

| Column | Type | Notes |
|---|---|---|
| `id` | int | Unique within a portal table |
| `title` | varchar(256) | As published |
| `url` | varchar(512) | Public posting URL, kept as is |
| `location` | varchar(256) | As published |
| `posted` | varchar | As shown on the portal; free text on some portals (e.g. `Πριν 3 ώρες`), so not used as a date |
| `scraped` | timestamp | Collection time. **The date used** for the sample window and all filtering |
| `company` | varchar(256) | As published |
| `description` | text | As published |
| `type` | varchar(64) | Contract / employment type as published |

## Processing applied

None. The postings are published exactly as they appeared on the portals, including any contact details the employer chose to include.

## Rebuilding the sample (maintainer only)

1. Put the raw dumps in `raw_dumps/` (gitignored, never committed).
2. Start a clean DB: `docker compose down -v` then `docker compose up -d --wait db`.
3. Load: `docker compose exec db sh /tools/load_raw.sh`
4. Validate ids and write the manifest: `uv run python -m jobpipe.sample`
5. Export: `docker compose exec db sh /tools/export_seed.sh`
6. Move `dumps/02_raw_schema.sql` and `dumps/03_raw_seed.sql.gz` into `docker/mariadb/init/`.
7. Verify from zero: `docker compose down -v`, `docker compose up -d --wait db`, `uv run pytest -m db`.

## Terms

Included for demonstration and research reproducibility only. Not covered by the repository's MIT licence.
