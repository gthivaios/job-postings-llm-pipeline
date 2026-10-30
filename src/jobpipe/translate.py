"""Stage 2, translate: title, job type and description to English.

For every selected posting:
  1. normalize_text() on each field; split the description into chunks
  2. translate each distinct text once (LLM response cache, parallel calls)
  3. en_description = en_title + en_job_type + translated description

Only postings with en_description IS NULL are selected, so re-runs continue where they
stopped. Database work happens in the main thread; only the LLM calls run in parallel.

    uv run python -m jobpipe.translate --list-days
    uv run python -m jobpipe.translate --date 2026-04-01 --dry-run
    uv run python -m jobpipe.translate --date 2026-04-01 [--model qwen-2.5-7b] [--limit 50]
"""

import argparse
import hashlib
import logging
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import Connection, bindparam, create_engine, func, insert, select, text, update

from jobpipe import tracing
from jobpipe.config import Settings
from jobpipe.db.schema import llm_cache, unified_postings
from jobpipe.llm import MODELS, ChatModel, LLMResult, OpenRouterChat
from jobpipe.text import normalize_text, split_text_into_chunks

log = logging.getLogger(__name__)

PROMPT_VERSION = "translate-v1"  # bump when SYSTEM_PROMPT changes: invalidates the cache
SYSTEM_PROMPT = """You are a professional translator of job postings.
Translate the user's text into English. The text is usually Greek, but it may be in another \
language or already in English; if it is already English, return it unchanged.
Rules:
- Output only the translation: no explanations, notes, labels or quotation marks.
- Keep company names, brand names, acronyms, numbers and salaries unchanged.
- Translate faithfully: do not summarise, shorten or add information."""

BATCH_SIZE = 50  # postings per DB transaction: progress survives a crash

_QUOTES = {'"': '"', "'": "'", "«": "»", "“": "”"}
_LABEL = re.compile(r"^\s*(translation|english|english translation)\s*:\s*", re.IGNORECASE)


def clean_translation(raw: str) -> str:
    """Strip labels and wrapping quotes that small models sometimes add."""
    out = _LABEL.sub("", raw.strip())
    if len(out) >= 2 and _QUOTES.get(out[0]) == out[-1]:
        out = out[1:-1].strip()
    return out


def cache_key(model: str, text_in: str) -> str:
    return hashlib.sha256(f"{model}|{PROMPT_VERSION}|{text_in}".encode()).hexdigest()


@dataclass
class Segments:
    """A posting split into the texts that get translated."""

    uid: str
    title: str
    job_type: str
    description_chunks: list[str]

    def texts(self) -> list[str]:
        return [t for t in [self.title, self.job_type, *self.description_chunks] if t]


def prepare_segments(row, settings: Settings) -> Segments:
    form = settings.unicode_form
    return Segments(
        uid=row.uid,
        title=normalize_text(row.title, form),
        job_type=normalize_text(row.job_type, form),
        description_chunks=split_text_into_chunks(
            normalize_text(row.description, form),
            max_words=settings.chunk_max_words,
            max_chars=settings.chunk_max_chars,
        ),
    )


def build_en_description(en_title: str, en_job_type: str, en_body: str) -> str:
    return "\n\n".join(part for part in [en_title, en_job_type, en_body] if part)


@dataclass
class RunStats:
    postings_done: int = 0
    postings_failed: int = 0
    llm_calls: int = 0
    cache_hits: int = 0
    cost_usd: float = 0.0
    latencies_ms: list[int] = field(default_factory=list)

    def summary(self) -> str:
        lat = sorted(self.latencies_ms)
        p50 = statistics.median(lat) if lat else 0
        p95 = lat[min(len(lat) - 1, int(len(lat) * 0.95))] if lat else 0
        return (
            f"postings translated: {self.postings_done}, failed: {self.postings_failed} | "
            f"LLM calls: {self.llm_calls}, cache hits: {self.cache_hits} | "
            f"cost: ${self.cost_usd:.4f} | latency p50 {p50:.0f} ms, p95 {p95:.0f} ms"
        )


@tracing.track(name="translate_text")
def translate_text(llm: ChatModel, text_in: str, segment: str, uids: list[str]) -> LLMResult:
    """One translation call. Traced as its own Opik trace with the LLM call as a child span."""
    tracing.update_trace(
        metadata={"segment": segment, "uids": uids, "prompt_version": PROMPT_VERSION},
        tags=["translate", llm.model],
    )
    result = llm.complete(SYSTEM_PROMPT, text_in)
    return LLMResult(**{**result.__dict__, "text": clean_translation(result.text)})


def select_postings(
    conn: Connection, day: date, portal: str | None = None, limit: int | None = None
) -> list:
    start = datetime.combine(day, datetime.min.time())
    q = (
        select(
            unified_postings.c.uid,
            unified_postings.c.title,
            unified_postings.c.description,
            unified_postings.c.job_type,
        )
        .where(unified_postings.c.en_description.is_(None))
        .where(unified_postings.c.scraped >= start)
        .where(unified_postings.c.scraped < start + timedelta(days=1))
        .order_by(unified_postings.c.uid)
    )
    if portal:
        q = q.where(unified_postings.c.portal == portal)
    if limit:
        q = q.limit(limit)
    return conn.execute(q).all()


def _segment_kinds(postings: list[Segments]) -> tuple[dict[str, str], dict[str, list[str]]]:
    """For each distinct text: which kind of field it is, and which postings use it."""
    kind, users = {}, {}
    for p in postings:
        named = [(p.title, "title"), (p.job_type, "job_type")]
        named += [(c, "description") for c in p.description_chunks]
        for t, k in named:
            if t:
                kind.setdefault(t, k)
                users.setdefault(t, []).append(p.uid)
    return kind, users


def translate_batch(
    conn: Connection, llm: ChatModel, postings: list[Segments], workers: int, stats: RunStats
) -> None:
    kind, users = _segment_kinds(postings)
    keys = {t: cache_key(llm.model, t) for t in kind}

    # 1. cache lookup
    cached = {
        r.cache_key: r.response
        for r in conn.execute(
            select(llm_cache.c.cache_key, llm_cache.c.response).where(
                llm_cache.c.cache_key.in_(list(keys.values()))
            )
        )
    }
    translated: dict[str, str] = {t: cached[k] for t, k in keys.items() if k in cached}
    stats.cache_hits += len(translated)

    # 2. parallel LLM calls for the rest
    fresh: dict[str, LLMResult] = {}
    failed_texts: set[str] = set()
    missing = [t for t in kind if t not in translated]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(translate_text, llm, t, kind[t], users[t]): t for t in missing}
        for fut in as_completed(futures):
            t = futures[fut]
            try:
                fresh[t] = fut.result()
            except Exception as exc:  # one bad call must not stop the batch
                failed_texts.add(t)
                log.warning("translation failed (%s, %s): %s", kind[t], users[t][0], exc)

    # 3. store fresh results in the cache
    if fresh:
        conn.execute(
            insert(llm_cache),
            [
                {
                    "cache_key": keys[t],
                    "model": r.model,
                    "response": r.text,
                    "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens,
                    "cost_usd": r.cost_usd,
                    "latency_ms": r.latency_ms,
                }
                for t, r in fresh.items()
            ],
        )
    for t, r in fresh.items():
        translated[t] = r.text
        stats.llm_calls += 1
        stats.cost_usd += r.cost_usd
        stats.latencies_ms.append(r.latency_ms)

    # 4. assemble and write each posting. A text shared by several postings is charged
    #    to the first one, so SUM(translation_cost_usd) equals what was actually spent.
    charged: set[str] = set()
    now = datetime.now()
    updates = []
    for p in postings:
        if any(t in failed_texts for t in p.texts()):
            stats.postings_failed += 1  # stays NULL, picked up again on the next run
            continue
        own_fresh = [t for t in dict.fromkeys(p.texts()) if t in fresh and t not in charged]
        charged.update(own_fresh)
        en_title = translated.get(p.title, "")
        en_job_type = translated.get(p.job_type, "")
        en_body = " ".join(translated[c] for c in p.description_chunks if c)
        updates.append(
            {
                "b_uid": p.uid,
                "en_title": en_title,
                "en_job_type": en_job_type or None,
                "en_description": build_en_description(en_title, en_job_type, en_body),
                "translation_model": llm.model,
                "translated_at": now,
                "translation_cost_usd": sum(fresh[t].cost_usd for t in own_fresh),
                "translation_latency_ms": sum(fresh[t].latency_ms for t in own_fresh),
            }
        )
    if updates:
        conn.execute(
            update(unified_postings).where(unified_postings.c.uid == bindparam("b_uid")),
            updates,
        )
        stats.postings_done += len(updates)


def run(
    conn_factory,
    llm: ChatModel,
    settings: Settings,
    day: date,
    portal: str | None = None,
    limit: int | None = None,
    workers: int | None = None,
) -> RunStats:
    """Translate one day of postings, committing after every batch."""
    stats = RunStats()
    with conn_factory() as conn:
        rows = select_postings(conn, day, portal, limit)
    log.info("%d postings to translate for %s with %s", len(rows), day, llm.model)

    for i in range(0, len(rows), BATCH_SIZE):
        batch = [prepare_segments(r, settings) for r in rows[i : i + BATCH_SIZE]]
        with conn_factory() as conn:  # one transaction per batch
            translate_batch(conn, llm, batch, workers or settings.translate_workers, stats)
        log.info("  %d/%d  %s", min(i + BATCH_SIZE, len(rows)), len(rows), stats.summary())
    return stats


def dry_run(conn: Connection, settings: Settings, day: date, portal, limit, model: str) -> None:
    rows = select_postings(conn, day, portal, limit)
    segs = [prepare_segments(r, settings) for r in rows]
    texts = [t for s in segs for t in s.texts()]
    distinct = set(texts)
    cached = conn.execute(
        select(func.count()).where(
            llm_cache.c.cache_key.in_([cache_key(model, t) for t in distinct])
        )
    ).scalar_one()
    words = sum(len(t.split()) for t in distinct)
    log.info(
        "%s: %d postings -> %d texts, %d distinct, %d already cached; "
        "~%d words to translate (no API calls made)",
        day,
        len(rows),
        len(texts),
        len(distinct),
        cached,
        words,
    )


def list_days(conn: Connection) -> None:
    rows = conn.execute(
        text(
            "SELECT DATE(scraped) AS day, COUNT(*) AS n, COUNT(en_description) AS translated "
            "FROM unified_postings GROUP BY DATE(scraped) ORDER BY day"
        )
    ).all()
    log.info("%-12s %8s %11s", "day", "postings", "translated")
    for r in rows:
        log.info("%-12s %8d %11d", r.day, r.n, r.translated)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--date", type=date.fromisoformat, help="scraped day, YYYY-MM-DD")
    parser.add_argument("--portal", help="only this portal")
    parser.add_argument("--limit", type=int, help="at most N postings")
    parser.add_argument("--model", help=f"alias ({', '.join(MODELS)}) or OpenRouter id")
    parser.add_argument("--workers", type=int, help="parallel LLM calls")
    parser.add_argument("--dry-run", action="store_true", help="count work, call no API")
    parser.add_argument("--list-days", action="store_true", help="postings per day and progress")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    s = Settings()
    engine = create_engine(s.url(s.analysis_db))

    if args.list_days:
        with engine.connect() as conn:
            list_days(conn)
        return
    if not args.date:
        parser.error("--date is required (use --list-days to see available days)")

    model_name = args.model or s.translate_model
    if args.dry_run:
        from jobpipe.llm import resolve_model

        with engine.connect() as conn:
            dry_run(conn, s, args.date, args.portal, args.limit, resolve_model(model_name))
        return

    tracing.configure(s.tracing)
    llm = OpenRouterChat(model_name, s)
    started = time.perf_counter()
    try:
        stats = run(engine.begin, llm, s, args.date, args.portal, args.limit, args.workers)
    finally:
        tracing.flush()
    log.info("done in %.0f s | %s", time.perf_counter() - started, stats.summary())
    if tracing.enabled():
        log.info("traces: open your Opik project to inspect every call")


if __name__ == "__main__":
    main()
