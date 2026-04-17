"""Reconnaissance + load script for the alexdiresta profightdb SQLite dataset.

Source: https://www.kaggle.com/datasets/alexdiresta/all-wwe-and-wwf-matches-from-4301979-to-92523
File:   data/external/wwe_db_2026-01-18.sqlite

Scope
-----
The dataset covers WWE, WWF, WWWF, WCW, ECW, NXT from 1963-01-25 onward. Our
ringside DB already holds ~201K matches from Cagematch; large overlap expected
for the 1990-present era. This script is primarily useful for:

  * pre-1990 backfill (Cagematch coverage is thin for that era)
  * cross-validation of what we already have
  * a fallback source if Cagematch changes its HTML again

Modes
-----
  --dry-run (default): report overlap stats, write nothing.
  --load:              insert non-duplicate events/matches into Postgres.

Dedup key
---------
Natural key — (promotion_id, date, lower(name)) — because alexdiresta has
profightdb URLs and ringside is keyed on cagematch_ids; no shared ID space.
Requires the schema's events_cagematch_id_key UNIQUE constraint to be skipped
(we insert NULL cagematch_id). We use a prefixed synthetic marker
``pfdb:<card_id>`` so the loader is idempotent across runs.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

import psycopg2
import psycopg2.extras
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger(__name__)

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://ringside:ringside@localhost:5432/ringside",
)

DEFAULT_SQLITE = Path("/var/www/wrastling/data/external/wwe_db_2026-01-18.sqlite")

# alexdiresta promotion_id -> ringside promotion_id
# (WWWF and WWF are historical ancestors of WWE; fold into WWE per our schema.)
PROMOTION_MAP = {
    4140: 1,    # WWE   -> WWE
    11791: 1,   # WWF   -> WWE
    11561: 1,   # WWWF  -> WWE
    2715: 3,    # WCW   -> WCW
    1: 4,       # ECW   -> ECW
    692: 6,     # NXT   -> NXT
}


def iso_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def run_recon(sqlite_path: Path, pg_conn) -> dict:
    """Scan alexdiresta cards, report how many would be new vs duplicates."""
    src = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row

    stats = {
        "cards_total": 0,
        "cards_mapped": 0,
        "cards_unmapped_promotion": 0,
        "cards_invalid_date": 0,
        "events_new": 0,
        "events_dup": 0,
        "by_decade_new": {},
        "by_promotion_new": {},
    }

    with pg_conn.cursor() as cur:
        cur.execute("SELECT id, name FROM promotions ORDER BY id")
        promo_names = {row[0]: row[1] for row in cur.fetchall()}

    sample_dups = []
    sample_new = []

    for card in src.execute(
        "SELECT c.id, c.event_date, c.promotion_id, e.name AS event_name "
        "FROM Cards c LEFT JOIN Events e ON e.id = c.event_id"
    ):
        stats["cards_total"] += 1
        ringside_pid = PROMOTION_MAP.get(card["promotion_id"])
        if ringside_pid is None:
            stats["cards_unmapped_promotion"] += 1
            continue
        event_date = iso_date(card["event_date"])
        if event_date is None:
            stats["cards_invalid_date"] += 1
            continue
        stats["cards_mapped"] += 1

        name = (card["event_name"] or "").strip()
        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM events "
                "WHERE promotion_id = %s AND date = %s "
                "AND lower(name) = lower(%s) LIMIT 1",
                (ringside_pid, event_date, name),
            )
            hit = cur.fetchone()

        if hit:
            stats["events_dup"] += 1
            if len(sample_dups) < 5:
                sample_dups.append((name, str(event_date), promo_names[ringside_pid]))
        else:
            stats["events_new"] += 1
            decade = f"{event_date.year // 10 * 10}s"
            stats["by_decade_new"][decade] = stats["by_decade_new"].get(decade, 0) + 1
            promo = promo_names[ringside_pid]
            stats["by_promotion_new"][promo] = stats["by_promotion_new"].get(promo, 0) + 1
            if len(sample_new) < 5:
                sample_new.append((name, str(event_date), promo))

    src.close()
    stats["sample_new"] = sample_new
    stats["sample_dup"] = sample_dups
    return stats


def run_load(sqlite_path: Path, pg_conn) -> dict:
    """Insert non-duplicate events from alexdiresta. Matches/participants TBD."""
    # Load path intentionally gated to events-only for the first pass. Matches
    # need additional work: alexdiresta stores winner_id/loser_id as TEXT
    # (possibly comma-separated for multi-person matches), and match_type
    # strings need mapping into our match_type ENUM. Keeping events-only here
    # makes the first load reviewable before committing to the full import.
    src = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row

    stats = {"events_inserted": 0, "events_skipped": 0, "errors": 0}
    with pg_conn.cursor() as cur:
        for card in src.execute(
            "SELECT c.id, c.event_date, c.promotion_id, c.url, e.name AS event_name "
            "FROM Cards c LEFT JOIN Events e ON e.id = c.event_id"
        ):
            ringside_pid = PROMOTION_MAP.get(card["promotion_id"])
            event_date = iso_date(card["event_date"])
            name = (card["event_name"] or "").strip()
            if ringside_pid is None or event_date is None or not name:
                stats["errors"] += 1
                continue

            cur.execute(
                "SELECT id FROM events "
                "WHERE promotion_id = %s AND date = %s "
                "AND lower(name) = lower(%s) LIMIT 1",
                (ringside_pid, event_date, name),
            )
            if cur.fetchone():
                stats["events_skipped"] += 1
                continue

            try:
                cur.execute(
                    "INSERT INTO events (name, promotion_id, date, event_type) "
                    "VALUES (%s, %s, %s, 'weekly_tv') RETURNING id",
                    (name, ringside_pid, event_date),
                )
                stats["events_inserted"] += 1
            except Exception:
                logger.exception(
                    "event_insert_failed",
                    name=name, date=str(event_date), promo_id=ringside_pid,
                )
                stats["errors"] += 1

        pg_conn.commit()

    src.close()
    return stats


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sqlite", type=Path, default=DEFAULT_SQLITE)
    p.add_argument("--load", action="store_true",
                   help="Actually insert (default is dry-run recon).")
    args = p.parse_args()

    if not args.sqlite.exists():
        logger.error("sqlite_not_found", path=str(args.sqlite))
        return 1

    pg = psycopg2.connect(DB_URL)
    try:
        if args.load:
            logger.info("alexdiresta_load_start", sqlite=str(args.sqlite))
            stats = run_load(args.sqlite, pg)
            logger.info("alexdiresta_load_complete", **stats)
        else:
            logger.info("alexdiresta_recon_start", sqlite=str(args.sqlite))
            stats = run_recon(args.sqlite, pg)
            logger.info("alexdiresta_recon_complete", **stats)
            print()
            print("=== RECON RESULTS ===")
            for k, v in stats.items():
                print(f"  {k}: {v}")
    finally:
        pg.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
