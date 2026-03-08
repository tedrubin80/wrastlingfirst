"""Import: AEW Events & Match Ratings (franchise403) — 4K matches with CageMatch + WON ratings.

Same schema as the WWE ratings dataset but for AEW. Imports both events
(with venue/location/event type) and match-level data with ratings.
"""

import csv
import os
import re
from typing import Optional

import structlog

from .shared import (
    BaseImporter, PROMOTION_ALIASES, SUPPORTED_PROMOTIONS,
    map_win_type, classify_match_type, split_wrestler_name,
)

log = structlog.get_logger()

DATASET_ID = "franchise403/aew-events-and-match-ratings-20152025"


def get_dataset_path(explicit_path: Optional[str] = None) -> str:
    if explicit_path:
        return explicit_path
    import kagglehub
    return kagglehub.dataset_download(DATASET_ID)


def classify_aew_event_type(event_name: str, event_type_raw: str) -> str:
    """Infer event_type for AEW events."""
    et = event_type_raw.strip().lower()
    if "ppv" in et or "ple" in et:
        return "ppv"
    if "special" in et:
        return "special"

    name_lower = event_name.lower()
    if any(kw in name_lower for kw in ["all out", "revolution", "double or nothing",
                                         "full gear", "all in", "worlds end",
                                         "forbidden door", "dynasty"]):
        return "ppv"
    if "dark" in name_lower:
        return "house_show"  # Dark/Elevation treated as non-TV
    return "weekly_tv"


def parse_match_participants(match_desc: str) -> tuple[list[str], list[str]]:
    """Parse match description like 'A vs. B' or 'A & B vs. C & D' into winner/loser lists.

    AEW dataset lists Opponent1 as first listed (usually winner in standard format).
    """
    # The Match column has the full description, Opponent1/2 are pre-split
    # We'll use Opponent1/2 columns directly in the caller
    return [], []


def run(pg_dsn: str, dataset_path: Optional[str] = None):
    """Import AEW events and match ratings into Ringside DB."""
    base_path = get_dataset_path(dataset_path)
    events_csv = os.path.join(base_path, "aew_events.csv")
    ratings_csv = os.path.join(base_path, "aew_match_ratings.csv")

    log.info("AEW import starting", events=events_csv, ratings=ratings_csv)

    imp = BaseImporter(pg_dsn)
    imp.load_caches()

    # --- Step 1: Import events ---
    if os.path.exists(events_csv):
        with open(events_csv, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                date = (row.get("Date") or "").strip()
                promo_raw = (row.get("Promotion") or "").strip()
                abbrev = PROMOTION_ALIASES.get(promo_raw, promo_raw)
                if abbrev not in SUPPORTED_PROMOTIONS or not date:
                    imp.stats["skipped_unsupported"] += 1
                    continue

                event_name = (row.get("Event Name") or row.get("Event") or "").strip()
                if not event_name:
                    continue

                promotion_id = imp.ensure_promotion(abbrev)
                event_type_raw = (row.get("EventType") or "").strip()
                event_type = classify_aew_event_type(event_name, event_type_raw)

                city = (row.get("CityTown") or "").strip()
                state = (row.get("StateProvince") or "").strip()
                venue = (row.get("Location") or "").strip()

                imp.upsert_event(
                    name=event_name,
                    promotion_id=promotion_id,
                    date=date,
                    venue=venue,
                    city=city,
                    event_type=event_type,
                )

                if (i + 1) % 500 == 0:
                    imp.commit_batch("AEW events", i + 1, 0)

        imp.pg.commit()
        log.info("AEW events imported", **dict(imp.stats))

    # --- Step 2: Import matches with ratings ---
    if os.path.exists(ratings_csv):
        # Reset match counter for this phase
        match_count_before = imp.stats.get("matches_imported", 0)

        with open(ratings_csv, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                date = (row.get("Date") or "").strip()
                promo_raw = (row.get("Promotion") or "").strip()
                abbrev = PROMOTION_ALIASES.get(promo_raw, promo_raw)
                if abbrev not in SUPPORTED_PROMOTIONS or not date:
                    imp.stats["skipped_unsupported"] += 1
                    continue

                promotion_id = imp.ensure_promotion(abbrev)

                # Parse ratings
                rating = None
                cm_raw = (row.get("CageMatchRating") or "").strip()
                won_raw = (row.get("WONStarRating") or "").strip()

                if won_raw:
                    try:
                        rating = max(0.0, min(float(won_raw), 10.0))
                    except ValueError:
                        pass
                if rating is None and cm_raw:
                    try:
                        rating = max(0.0, min(float(cm_raw) / 2.0, 10.0))
                    except ValueError:
                        pass

                # Parse opponents
                opp1 = (row.get("Opponent1") or row.get("Opponent.1") or "").strip()
                opp2 = (row.get("Opponent2") or row.get("Opponent.2") or "").strip()
                # Clean trailing commas
                opp1 = opp1.rstrip(",").strip()
                opp2 = opp2.rstrip(",").strip()

                if not opp1 and not opp2:
                    imp.stats["skipped_no_participants"] += 1
                    continue

                # Parse match description for match type hints
                match_desc = (row.get("Match") or "").strip()
                match_type = classify_match_type(match_desc)

                # Detect title match from description
                desc_lower = match_desc.lower()
                is_title = any(kw in desc_lower for kw in [
                    "championship", "title", "world champion", "tnt champion",
                    "tbs champion", "tag team champion"
                ])

                # Find or create event for this date
                # Use generic event name since we may not have exact event info
                event_id = imp.upsert_event(
                    name=f"AEW Show ({date})",
                    promotion_id=promotion_id,
                    date=date,
                )

                # Check if match already exists (by event + participant)
                winners = split_wrestler_name(opp1) if opp1 else []
                losers = split_wrestler_name(opp2) if opp2 else []

                if winners:
                    with imp.pg.cursor() as cur:
                        first_name = winners[0]
                        key = first_name.lower().strip()
                        if key in imp._wrestler_cache:
                            cur.execute(
                                """SELECT m.id FROM matches m
                                   JOIN match_participants mp ON mp.match_id = m.id
                                   WHERE m.event_id = %s AND mp.wrestler_id = %s
                                   LIMIT 1""",
                                (event_id, imp._wrestler_cache[key]),
                            )
                            if cur.fetchone():
                                # Match exists — just update rating if we have one
                                if rating is not None:
                                    cur.execute(
                                        """UPDATE matches m SET rating = %s
                                           FROM match_participants mp
                                           WHERE m.id = mp.match_id
                                             AND m.event_id = %s
                                             AND mp.wrestler_id = %s
                                             AND m.rating IS NULL""",
                                        (rating, event_id, imp._wrestler_cache[key]),
                                    )
                                    if cur.rowcount > 0:
                                        imp.stats["ratings_applied"] += 1
                                imp.stats["matches_already_exist"] += 1
                                continue

                # Insert new match
                match_id = imp.insert_match(
                    event_id=event_id,
                    match_order=i + 1,
                    match_type=match_type,
                    duration_secs=None,
                    title_match=is_title,
                    rating=rating,
                )

                # Opp1 = winner (first listed), Opp2 = loser
                imp.insert_participants(
                    match_id, winners, losers, promotion_id
                )

                if (i + 1) % 1000 == 0:
                    imp.commit_batch("AEW matches", i + 1, 0)

        imp.pg.commit()
        log.info("AEW matches imported", **dict(imp.stats))

    imp.close()
    return dict(imp.stats)
