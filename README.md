# jobpipe

A modular LLM pipeline that turns raw multilingual job postings into structured, taxonomy-normalised data (ESCO, NACE, ISCED).

> Work in progress: being rebuilt stage by stage. Current stage: **reproducible sample database**.

## Quick start

Requirements: Docker Desktop, [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/gthivaios/<repo-name>.git
cd <repo-name>
cp .env.example .env            # Windows PowerShell: Copy-Item .env.example .env
docker compose up -d --wait db  # first start loads the sample data
uv sync
uv run alembic upgrade head     # creates the analysis tables
uv run python -m jobpipe.ingest # stage 1: raw portals -> unified_postings
uv run pytest -m db             # checks the sample and the ingest
```

To reload from scratch: `docker compose down -v` then `docker compose up -d --wait db`.

## Pipeline

| Stage | Module | Output |
|---|---|---|
| 1. Ingest | `jobpipe.ingest` | `unified_postings`: one row per posting across all portals, with `portal` and a deterministic `uid` |
| 2. Translate | _next_ | |
| 3. Deduplicate | | |
| 4. Extract metadata | | |
| 5. Normalise (ESCO, NACE, ISCED) | | |

`uid` is the first 16 hex characters of `sha256("<portal>:<source_id>")`. The same posting gets the same `uid` on every rebuild, so evaluation sets and traces can refer to it safely.

## Sample data

Raw postings from 6 Greek job portals over 10 days, as published. See [`data/README.md`](data/README.md).

## Roadmap

- [x] Repo setup, CI
- [ ] Reproducible sample DB
- [x] Analysis schema via migrations (Alembic)
- [x] Stage 1: unified ingest
- [ ] Pipeline stages: translate → dedup → extract → normalise
- [ ] Evaluation suite (Opik) with published results
- [ ] Full Docker Compose demo

## License

Code: MIT. The sample job postings are included for demonstration only and are not covered by this licence.
