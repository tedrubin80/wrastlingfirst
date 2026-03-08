"""Import #1: WWE SQLite dataset (alexdiresta) — 88K matches, 1963–2026."""

import glob
import os
import sqlite3
from typing import Optional

import structlog

from .shared import (
    BaseImporter, PROMOTION_ALIASES, SUPPORTED_PROMOTIONS,
    map_win_type, classify_match_type, parse_duration_mmss, split_wrestler_name,
)

log = structlog.get_logger()

DATASET_ID = "alexdiresta/all-wwe-and-wwf-matches-from-4301979-to-92523"


def get_sqlite_path(explicit_path: Optional[str] = None) -> str:
    if explicit_path:
        return explicit_path
    import kagglehub
    path = kagglehub.dataset_download(DATASET_ID)
    files = glob.glob(os.path.join(path, "*.sqlite"))
    if not files:
        raise FileNotFoundError(f"No .sqlite file in {path}")
    return files[0]


def run(pg_dsn: str, sqlite_path: Optional[str] = None):
    """Import WWE SQLite dataset into Ringside DB."""
    sqlite_path = get_sqlite_path(sqlite_path)
    log.info("WWE SQLite import starting", source=sqlite_path)

    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row
    imp = BaseImporter(pg_dsn)
    imp.load_caches()

    cur = src.cursor()

    # Pre-load Kaggle lookup tables
    cur.execute("SELECT id, name FROM Wrestlers")
    kg_wrestlers = {str(r["id"]): r["name"] for r in cur.fetchall()}

    cur.execute("SELECT id, name FROM Match_Types")
    kg_match_types = {str(r["id"]): r["name"] for r in cur.fetchall()}

    cur.execute("SELECT id, name FROM Belts")
    kg_belts = {str(r["id"]): r["name"] for r in cur.fetchall()}

    cur.execute("SELECT id, name FROM Promotions")
    kg_promos = {r["id"]: r["name"] for r in cur.fetchall()}

    # Load all cards
    cur.execute("""
        SELECT c.id AS card_id, c.event_date, c.promotion_id,
               e.name AS event_name, l.name AS location_name
        FROM Cards c
        JOIN Events e ON e.id = c.event_id
        LEFT JOIN Locations l ON l.id = c.location_id
        ORDER BY c.event_date
    """)
    cards = cur.fetchall()
    total = len(cards)
    log.info("Processing cards", total=total)

    for i, card in enumerate(cards):
        promo_name = kg_promos.get(card["promotion_id"], "")
        abbrev = PROMOTION_ALIASES.get(promo_name)
        if not abbrev or abbrev not in SUPPORTED_PROMOTIONS:
            imp.stats["skipped_unsupported_promo"] += 1
            continue

        if not card["event_date"]:
            imp.stats["skipped_no_date"] += 1
            continue

        promotion_id = imp.ensure_promotion(abbrev)
        event_id = imp.upsert_event(
            name=card["event_name"],
            promotion_id=promotion_id,
            date=card["event_date"],
            venue=card["location_name"] or "",
        )

        # Matches for this card
        cur2 = src.cursor()
        cur2.execute(
            "SELECT * FROM Matches WHERE card_id = ? ORDER BY id", (card["card_id"],)
        )
        for match_order, match in enumerate(cur2.fetchall(), 1):
            winner_name = kg_wrestlers.get(match["winner_id"] or "", "")
            loser_name = kg_wrestlers.get(match["loser_id"] or "", "")
            if not winner_name and not loser_name:
                imp.stats["skipped_no_participants"] += 1
                continue

            mt_name = kg_match_types.get(match["match_type_id"] or "", "")
            match_type = classify_match_type(mt_name)
            duration = parse_duration_mmss(match["duration"] or "")
            winner_result, loser_result = map_win_type(match["win_type"] or "def.")

            belt_name = kg_belts.get(match["title_id"] or "", "")
            is_title = bool(belt_name)

            match_id = imp.insert_match(
                event_id, match_order, match_type, duration, is_title
            )

            winners = split_wrestler_name(winner_name)
            losers = split_wrestler_name(loser_name)
            imp.insert_participants(
                match_id, winners, losers, promotion_id, winner_result, loser_result
            )

            # Title change
            if match["title_change"] and belt_name and winners:
                title_id = imp.resolve_title(belt_name, promotion_id)
                if title_id:
                    w_id = imp.resolve_wrestler(winners[0], promotion_id)
                    with imp.pg.cursor() as pgcur:
                        pgcur.execute(
                            "UPDATE title_reigns SET lost_date = %s WHERE title_id = %s AND lost_date IS NULL",
                            (card["event_date"], title_id),
                        )
                        pgcur.execute(
                            "INSERT INTO title_reigns (title_id, wrestler_id, won_date, defenses) VALUES (%s, %s, %s, 0)",
                            (title_id, w_id, card["event_date"]),
                        )
                        imp.stats["title_changes"] += 1

        if (i + 1) % 500 == 0:
            imp.commit_batch("WWE SQLite", i + 1, total)

    imp.pg.commit()
    log.info("WWE SQLite import complete", **dict(imp.stats))
    src.close()
    imp.close()
    return dict(imp.stats)
