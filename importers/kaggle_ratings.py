"""Import #3: WWE Events & Match Ratings 2015–2025 (franchise403).

This is an enrichment import — it adds CageMatch ratings and WON star ratings
to existing matches, and fills in event metadata (location, event type).
"""

import csv
import glob
import os
from typing import Optional

import structlog

from .shared import BaseImporter, PROMOTION_ALIASES, SUPPORTED_PROMOTIONS

log = structlog.get_logger()

DATASET_ID = "franchise403/wwe-events-and-match-ratings-20152025"


def get_dataset_path(explicit_path: Optional[str] = None) -> str:
    if explicit_path:
        return explicit_path
    import kagglehub
    return kagglehub.dataset_download(DATASET_ID)


def run(pg_dsn: str, dataset_path: Optional[str] = None):
    """Import ratings + event metadata into Ringside DB."""
    base_path = get_dataset_path(dataset_path)
    events_csv = os.path.join(base_path, "wwe_events.csv")
    ratings_csv = os.path.join(base_path, "wwe_match_rating.csv")

    log.info("Ratings import starting", events=events_csv, ratings=ratings_csv)

    imp = BaseImporter(pg_dsn)
    imp.load_caches()

    # --- Step 1: Enrich events with location and event type ---
    if os.path.exists(events_csv):
        with open(events_csv, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                date = (row.get("Date") or "").strip()
                promo_raw = (row.get("Promotion") or "").strip()
                abbrev = PROMOTION_ALIASES.get(promo_raw, promo_raw)
                if abbrev not in SUPPORTED_PROMOTIONS or not date:
                    continue

                event_name = (row.get("EventName") or row.get("Event") or "").strip()
                if not event_name:
                    continue

                promotion_id = imp.ensure_promotion(abbrev)

                # Determine event type
                event_type_raw = (row.get("EventType") or "").strip().lower()
                if "non-televised" in event_type_raw or "non televised" in event_type_raw:
                    event_type = "house_show"
                elif "pay-per-view" in event_type_raw or "ppv" in event_type_raw:
                    event_type = "ppv"
                elif "special" in event_type_raw:
                    event_type = "special"
                else:
                    event_type = "weekly_tv"

                city = (row.get("CityTown") or "").strip()
                state = (row.get("StateProvince") or "").strip()
                venue = (row.get("Location") or "").strip()

                # Update existing event or create
                with imp.pg.cursor() as cur:
                    cur.execute(
                        """UPDATE events SET
                             venue = COALESCE(NULLIF(%s, ''), venue),
                             city = COALESCE(NULLIF(%s, ''), city),
                             state = COALESCE(NULLIF(%s, ''), state),
                             event_type = %s
                           WHERE name = %s AND promotion_id = %s AND date = %s""",
                        (venue, city, state, event_type, event_name, promotion_id, date),
                    )
                    if cur.rowcount > 0:
                        imp.stats["events_enriched"] += 1
                    else:
                        # Event not found — create it
                        imp.upsert_event(
                            name=event_name,
                            promotion_id=promotion_id,
                            date=date,
                            venue=venue,
                            city=city,
                            event_type=event_type,
                        )

                if (i + 1) % 1000 == 0:
                    imp.commit_batch("Events enrichment", i + 1, 0)

        imp.pg.commit()
        log.info("Events enrichment done", **dict(imp.stats))

    # --- Step 2: Import match ratings ---
    if os.path.exists(ratings_csv):
        with open(ratings_csv, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                date = (row.get("Date") or "").strip()
                promo_raw = (row.get("Promotion") or "").strip()
                abbrev = PROMOTION_ALIASES.get(promo_raw, promo_raw)
                if abbrev not in SUPPORTED_PROMOTIONS or not date:
                    continue

                # Parse ratings
                cm_rating = None
                cm_raw = (row.get("CageMatchRating") or "").strip()
                if cm_raw:
                    try:
                        cm_rating = float(cm_raw)
                    except ValueError:
                        pass

                won_rating = None
                won_raw = (row.get("WONStarRating") or "").strip()
                if won_raw:
                    try:
                        won_rating = float(won_raw)
                    except ValueError:
                        pass

                if cm_rating is None and won_rating is None:
                    imp.stats["skipped_no_ratings"] += 1
                    continue

                # Try to match existing match by date + participants
                # Use CageMatch rating as the primary rating (0-10 scale → 0-5)
                rating = won_rating if won_rating else (cm_rating / 2.0 if cm_rating else None)

                # Match description to find the match
                match_desc = (row.get("Match") or "").strip()
                opponent1 = (row.get("Opponent.1") or "").strip()
                opponent2 = (row.get("Opponent.2") or "").strip()

                promotion_id = imp.ensure_promotion(abbrev)

                # Try to update rating on matches from that date
                # Match by date + any participant name
                search_name = opponent1 or opponent2
                if not search_name:
                    imp.stats["skipped_no_opponent"] += 1
                    continue

                with imp.pg.cursor() as cur:
                    cur.execute(
                        """UPDATE matches m SET rating = %s
                           FROM events e, match_participants mp, wrestlers w
                           WHERE m.event_id = e.id
                             AND mp.match_id = m.id
                             AND w.id = mp.wrestler_id
                             AND e.date = %s
                             AND e.promotion_id = %s
                             AND lower(w.ring_name) = lower(%s)
                             AND m.rating IS NULL""",
                        (rating, date, promotion_id, search_name),
                    )
                    if cur.rowcount > 0:
                        imp.stats["ratings_applied"] += cur.rowcount
                    else:
                        imp.stats["ratings_unmatched"] += 1

                if (i + 1) % 1000 == 0:
                    imp.commit_batch("Ratings", i + 1, 0)

        imp.pg.commit()
        log.info("Ratings import done", **dict(imp.stats))

    imp.close()
    return dict(imp.stats)
