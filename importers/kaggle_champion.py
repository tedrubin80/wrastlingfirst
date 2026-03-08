"""Import #4: WWE Champion Dataset (waqi786) — 1K matches with title flags.

This is a small enrichment dataset. It adds title_match flags to matches
that may not have been tagged in the other datasets.
"""

import csv
import glob
import os
from typing import Optional

import structlog

from .shared import (
    BaseImporter, PROMOTION_ALIASES, SUPPORTED_PROMOTIONS,
    map_win_type, classify_match_type, split_wrestler_name,
)

log = structlog.get_logger()

DATASET_ID = "waqi786/wwe-champion-dataset"


def get_csv_path(explicit_path: Optional[str] = None) -> str:
    if explicit_path:
        return explicit_path
    import kagglehub
    path = kagglehub.dataset_download(DATASET_ID)
    files = glob.glob(os.path.join(path, "*.csv"))
    if not files:
        raise FileNotFoundError(f"No .csv in {path}")
    return files[0]


def run(pg_dsn: str, csv_path: Optional[str] = None):
    """Import WWE Champion dataset — enriches title match flags."""
    csv_path = get_csv_path(csv_path)
    log.info("Champion dataset import starting", source=csv_path)

    imp = BaseImporter(pg_dsn)
    imp.load_caches()

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            date = (row.get("Date") or "").strip()
            event_name = (row.get("Event") or "").strip()
            winner = (row.get("Winner") or "").strip()
            loser = (row.get("Loser") or "").strip()
            is_title = (row.get("Title Match") or "").strip().lower() == "yes"

            if not date or not winner:
                imp.stats["skipped_incomplete"] += 1
                continue

            # Default to WWE
            abbrev = "WWE"
            promotion_id = imp.ensure_promotion(abbrev)

            # Try to find and update existing match
            if is_title and winner:
                with imp.pg.cursor() as cur:
                    cur.execute(
                        """UPDATE matches m SET title_match = true
                           FROM events e, match_participants mp, wrestlers w
                           WHERE m.event_id = e.id
                             AND mp.match_id = m.id
                             AND w.id = mp.wrestler_id
                             AND e.date = %s
                             AND lower(w.ring_name) = lower(%s)
                             AND m.title_match = false""",
                        (date, winner),
                    )
                    if cur.rowcount > 0:
                        imp.stats["title_flags_applied"] += cur.rowcount
                    else:
                        imp.stats["title_flags_unmatched"] += 1

            # Also insert if not already in DB
            event_id = imp.upsert_event(
                name=event_name or "WWE Event",
                promotion_id=promotion_id,
                date=date,
                event_type="ppv" if event_name else "weekly_tv",
            )

            # Check if match already exists for this event + wrestler
            with imp.pg.cursor() as cur:
                cur.execute(
                    """SELECT m.id FROM matches m
                       JOIN match_participants mp ON mp.match_id = m.id
                       JOIN wrestlers w ON w.id = mp.wrestler_id
                       WHERE m.event_id = %s AND lower(w.ring_name) = lower(%s)
                       LIMIT 1""",
                    (event_id, winner),
                )
                if cur.fetchone():
                    imp.stats["matches_already_exist"] += 1
                    continue

            # New match — insert it
            match_id = imp.insert_match(
                event_id=event_id,
                match_order=i + 1,
                match_type="singles",
                duration_secs=None,
                title_match=is_title,
            )

            winners = split_wrestler_name(winner)
            losers = split_wrestler_name(loser) if loser else []
            imp.insert_participants(match_id, winners, losers, promotion_id)

        if (i + 1) % 200 == 0:
            imp.commit_batch("Champion", i + 1, 0)

    imp.pg.commit()
    log.info("Champion dataset import complete", **dict(imp.stats))
    imp.close()
    return dict(imp.stats)
