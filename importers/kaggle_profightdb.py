"""Import #2: ProFightDB dataset (robbiemarriage) — 363K matches, multi-promotion."""

import csv
import glob
import os
import re
from datetime import datetime
from typing import Optional

import structlog

from .shared import (
    BaseImporter, PROMOTION_ALIASES, SUPPORTED_PROMOTIONS,
    map_win_type, classify_match_type, split_wrestler_name,
)

log = structlog.get_logger()

DATASET_ID = "robbiemarriage/profightdb-wrestling-match-database"

MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def parse_profightdb_date(date_str: str, year: str) -> Optional[str]:
    """Parse 'Tue, Sep 17th 2024' → '2024-09-17'."""
    if not date_str or not year:
        return None
    try:
        # Extract month and day number
        m = re.search(r'(\w{3})\s+(\d+)', date_str)
        if not m:
            return None
        month_str, day_str = m.group(1), m.group(2)
        month = MONTH_MAP.get(month_str)
        if not month:
            return None
        return f"{int(year):04d}-{month:02d}-{int(day_str):02d}"
    except (ValueError, TypeError):
        return None


def get_csv_path(explicit_path: Optional[str] = None) -> str:
    if explicit_path:
        return explicit_path
    import kagglehub
    path = kagglehub.dataset_download(DATASET_ID)
    files = glob.glob(os.path.join(path, "*.csv"))
    if not files:
        raise FileNotFoundError(f"No .csv file in {path}")
    return files[0]


def classify_event_type(event_name: str, ppv: str) -> str:
    """Infer event_type from name and PPV flag."""
    if ppv and ppv.lower() == "yes":
        return "ppv"
    name_lower = event_name.lower()
    if any(kw in name_lower for kw in ["wrestlemania", "summerslam", "royal rumble",
                                         "survivor series", "money in the bank"]):
        return "ppv"
    if "tv" in name_lower or "raw" in name_lower or "smackdown" in name_lower:
        return "weekly_tv"
    if "house" in name_lower or "live event" in name_lower:
        return "house_show"
    return "weekly_tv"


def run(pg_dsn: str, csv_path: Optional[str] = None):
    """Import ProFightDB dataset into Ringside DB."""
    csv_path = get_csv_path(csv_path)
    log.info("ProFightDB import starting", source=csv_path)

    imp = BaseImporter(pg_dsn)
    imp.load_caches()

    # Count total rows for progress
    with open(csv_path, encoding="latin-1") as f:
        total = sum(1 for _ in f) - 1  # minus header
    log.info("Total rows", count=total)

    # Track events per card to assign match_order
    event_match_counter: dict[str, int] = {}

    with open(csv_path, encoding="latin-1") as f:
        reader = csv.DictReader(f)

        for i, row in enumerate(reader):
            promo_raw = (row.get("Promotion") or "").strip()
            abbrev = PROMOTION_ALIASES.get(promo_raw, promo_raw)
            if abbrev not in SUPPORTED_PROMOTIONS:
                imp.stats["skipped_unsupported_promo"] += 1
                continue

            date = parse_profightdb_date(row.get("Date", ""), row.get("Year", ""))
            if not date:
                imp.stats["skipped_bad_date"] += 1
                continue

            event_name = (row.get("Event") or "Unknown Event").strip()
            promotion_id = imp.ensure_promotion(abbrev)

            event_type = classify_event_type(event_name, row.get("PPV", ""))
            event_id = imp.upsert_event(
                name=event_name,
                promotion_id=promotion_id,
                date=date,
                venue=(row.get("Venue") or "").strip(),
                city=(row.get("City") or "").strip(),
                event_type=event_type,
            )

            # Match order within event
            event_key = f"{event_id}"
            card_pos = row.get("Match.Card.Placement", "")
            try:
                match_order = int(card_pos)
            except (ValueError, TypeError):
                event_match_counter[event_key] = event_match_counter.get(event_key, 0) + 1
                match_order = event_match_counter[event_key]

            # Match type
            match_type = classify_match_type(row.get("Match.Type", ""))

            # Duration
            duration = None
            total_secs = row.get("Total.Seconds", "")
            if total_secs and total_secs != "NA":
                try:
                    duration = int(float(total_secs))
                except ValueError:
                    pass

            # Rating — clamp to valid range (schema CHECK: 0.00–10.00)
            rating = None
            meltzer = row.get("Meltzer.Rating", "")
            if meltzer and meltzer != "NA":
                try:
                    val = float(meltzer)
                    # Meltzer scale is -5 to 7; normalize negatives to 0
                    rating = max(0.0, min(val, 10.0))
                except ValueError:
                    pass

            # Title match
            championship = (row.get("Championship") or "").strip()
            is_title = bool(championship and championship.upper() != "NA")

            winner_name = (row.get("Winner") or "").strip()
            loser_name = (row.get("Loser") or "").strip()
            if not winner_name and not loser_name:
                imp.stats["skipped_no_participants"] += 1
                continue

            result_str = (row.get("Result") or "def.").strip()
            winner_result, loser_result = map_win_type(result_str)

            match_id = imp.insert_match(
                event_id, match_order, match_type, duration, is_title, rating
            )

            winners = split_wrestler_name(winner_name)
            losers = split_wrestler_name(loser_name)
            imp.insert_participants(
                match_id, winners, losers, promotion_id, winner_result, loser_result
            )

            if (i + 1) % 5000 == 0:
                imp.commit_batch("ProFightDB", i + 1, total)

    imp.pg.commit()
    log.info("ProFightDB import complete", **dict(imp.stats))
    imp.close()
    return dict(imp.stats)
