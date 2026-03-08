"""Shared utilities for all Kaggle importers."""

import re
from collections import defaultdict
from typing import Optional

import psycopg2
import structlog

log = structlog.get_logger()

# Promotion name variations → our abbreviation
PROMOTION_ALIASES: dict[str, str] = {
    "WWE": "WWE",
    "WWF": "WWE",
    "WWWF": "WWE",
    "WCW": "WCW",
    "ECW": "ECW",
    "NXT": "NXT",
    "TNA": "TNA",
    "AEW": "AEW",
    # Extended promotions we may want later
    "NJPW": "NJPW",
    "ROH": "ROH",
    "NWA": "NWA",
}

# Only import these promotions (matches our schema)
SUPPORTED_PROMOTIONS = {"WWE", "WCW", "ECW", "NXT", "TNA", "AEW"}


def map_win_type(win_type: str) -> tuple[str, str]:
    """Map win_type string → (winner_result, loser_result)."""
    wt = (win_type or "").strip().lower()
    if wt.startswith("draw") or wt == "vs." or wt == "nc" or "no contest" in wt:
        if "nc" in wt or "no contest" in wt:
            return ("no_contest", "no_contest")
        if "ddq" in wt:
            return ("dq", "dq")
        if "dco" in wt:
            return ("countout", "countout")
        return ("draw", "draw")
    if "(dq)" in wt or "disqualification" in wt:
        return ("win", "dq")
    if "(co)" in wt or "count out" in wt or "countout" in wt:
        return ("win", "countout")
    return ("win", "loss")


def classify_match_type(name: str) -> str:
    """Map free-text match type to our match_type enum."""
    if not name or name.strip().upper() == "NA":
        return "singles"
    n = name.lower().strip().strip('"')
    if "tag" in n:
        return "tag_team"
    if "triple threat" in n or "three-way" in n or "3-way" in n:
        return "triple_threat"
    if "fatal four" in n or "fatal 4" in n or "4-way" in n:
        return "fatal_four_way"
    if "battle royal" in n or "battle royale" in n:
        return "battle_royal"
    if "royal rumble" in n:
        return "royal_rumble"
    if "ladder" in n:
        return "ladder"
    if "tlc" in n or "tables, ladders" in n:
        return "tlc"
    if "hell in a cell" in n or "hiac" in n:
        return "hell_in_a_cell"
    if "cage" in n or "steel cage" in n or "war games" in n:
        return "cage"
    if "elimination chamber" in n:
        return "elimination_chamber"
    if "iron man" in n or "ironman" in n:
        return "iron_man"
    if "i quit" in n:
        return "i_quit"
    if "last man standing" in n:
        return "last_man_standing"
    if "table" in n:
        return "tables"
    if "handicap" in n:
        return "handicap"
    if "gauntlet" in n:
        return "gauntlet"
    return "other" if n else "singles"


def split_wrestler_name(name: str) -> list[str]:
    """Split tag team names: 'A & B' → ['A', 'B']."""
    if not name:
        return []
    parts = re.split(r'\s+&\s+', name.strip())
    return [p.strip() for p in parts if p.strip()]


def parse_duration_mmss(duration_str: str) -> Optional[int]:
    """Parse 'MM:SS' or 'M:SS' → seconds."""
    if not duration_str or not duration_str.strip():
        return None
    m = re.match(r"(\d+):(\d+)", duration_str.strip())
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return None


class BaseImporter:
    """Shared state and helpers for all importers."""

    def __init__(self, pg_dsn: str):
        self.pg = psycopg2.connect(pg_dsn)
        self.pg.autocommit = False

        self._wrestler_cache: dict[str, int] = {}
        self._promotion_cache: dict[str, int] = {}
        self._title_cache: dict[str, int] = {}
        self._event_cache: dict[str, int] = {}  # (name, promo_id, date) → id
        self.stats: dict[str, int] = defaultdict(int)

    def load_caches(self):
        """Load promotions, wrestlers, aliases into memory."""
        with self.pg.cursor() as cur:
            cur.execute("SELECT id, abbreviation FROM promotions")
            for row in cur.fetchall():
                self._promotion_cache[row[1]] = row[0]

            cur.execute("SELECT id, lower(ring_name) FROM wrestlers")
            for row in cur.fetchall():
                self._wrestler_cache[row[1]] = row[0]

            cur.execute("SELECT wrestler_id, lower(alias) FROM wrestler_aliases")
            for row in cur.fetchall():
                if row[1] not in self._wrestler_cache:
                    self._wrestler_cache[row[1]] = row[0]

        log.info("Caches loaded",
                 promotions=len(self._promotion_cache),
                 wrestlers=len(self._wrestler_cache))

    def ensure_promotion(self, abbrev: str) -> Optional[int]:
        """Get promotion ID, creating if needed."""
        if abbrev in self._promotion_cache:
            return self._promotion_cache[abbrev]

        with self.pg.cursor() as cur:
            cur.execute(
                """INSERT INTO promotions (name, abbreviation)
                   VALUES (%s, %s)
                   ON CONFLICT (abbreviation) DO UPDATE SET abbreviation = EXCLUDED.abbreviation
                   RETURNING id""",
                (abbrev, abbrev),
            )
            pid = cur.fetchone()[0]
            self._promotion_cache[abbrev] = pid
            return pid

    def resolve_wrestler(self, name: str, promotion_id: int) -> int:
        """Find or create wrestler by name."""
        key = name.lower().strip()
        if key in self._wrestler_cache:
            return self._wrestler_cache[key]

        with self.pg.cursor() as cur:
            cur.execute(
                """INSERT INTO wrestlers (ring_name, primary_promotion_id, status)
                   VALUES (%s, %s, 'inactive')
                   RETURNING id""",
                (name.strip(), promotion_id),
            )
            wid = cur.fetchone()[0]
            cur.execute(
                """INSERT INTO wrestler_aliases (wrestler_id, alias, promotion_id)
                   VALUES (%s, %s, %s)
                   ON CONFLICT DO NOTHING""",
                (wid, name.strip(), promotion_id),
            )
        self._wrestler_cache[key] = wid
        self.stats["wrestlers_created"] += 1
        return wid

    def resolve_title(self, belt_name: str, promotion_id: int) -> Optional[int]:
        """Find or create a title."""
        if not belt_name or belt_name.strip().upper() == "NA":
            return None
        key = belt_name.strip().lower()
        if key in self._title_cache:
            return self._title_cache[key]

        with self.pg.cursor() as cur:
            cur.execute("SELECT id FROM titles WHERE lower(name) = %s", (key,))
            row = cur.fetchone()
            if row:
                self._title_cache[key] = row[0]
                return row[0]
            cur.execute(
                "INSERT INTO titles (name, promotion_id) VALUES (%s, %s) RETURNING id",
                (belt_name.strip(), promotion_id),
            )
            tid = cur.fetchone()[0]
            self._title_cache[key] = tid
            self.stats["titles_created"] += 1
            return tid

    def upsert_event(self, name: str, promotion_id: int, date: str,
                     venue: str = "", city: str = "",
                     event_type: str = "weekly_tv") -> int:
        """Find or create event. Returns event ID."""
        cache_key = f"{name}|{promotion_id}|{date}"
        if cache_key in self._event_cache:
            return self._event_cache[cache_key]

        with self.pg.cursor() as cur:
            # Try to find existing
            cur.execute(
                "SELECT id FROM events WHERE name = %s AND promotion_id = %s AND date = %s",
                (name, promotion_id, date),
            )
            row = cur.fetchone()
            if row:
                self._event_cache[cache_key] = row[0]
                self.stats["events_existing"] += 1
                return row[0]

            cur.execute(
                """INSERT INTO events (name, promotion_id, date, venue, city, event_type)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (name, promotion_id, date, venue, city, event_type),
            )
            eid = cur.fetchone()[0]
            self._event_cache[cache_key] = eid
            self.stats["events_created"] += 1
            return eid

    def insert_match(self, event_id: int, match_order: int, match_type: str,
                     duration_secs: Optional[int], title_match: bool,
                     rating: Optional[float] = None) -> int:
        """Insert a match. Returns match ID."""
        with self.pg.cursor() as cur:
            cur.execute(
                """INSERT INTO matches (event_id, match_order, match_type,
                                       duration_seconds, title_match, rating)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (event_id, match_order, match_type, duration_secs, title_match, rating),
            )
            mid = cur.fetchone()[0]
            self.stats["matches_imported"] += 1
            return mid

    def insert_participants(self, match_id: int, winner_names: list[str],
                           loser_names: list[str], promotion_id: int,
                           winner_result: str = "win",
                           loser_result: str = "loss"):
        """Insert match participants for winners and losers."""
        with self.pg.cursor() as cur:
            for name in winner_names:
                wid = self.resolve_wrestler(name, promotion_id)
                cur.execute(
                    """INSERT INTO match_participants (match_id, wrestler_id, result)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (match_id, wrestler_id) DO NOTHING""",
                    (match_id, wid, winner_result),
                )
            for name in loser_names:
                lid = self.resolve_wrestler(name, promotion_id)
                cur.execute(
                    """INSERT INTO match_participants (match_id, wrestler_id, result)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (match_id, wrestler_id) DO NOTHING""",
                    (match_id, lid, loser_result),
                )

    def commit_batch(self, label: str, count: int, total: int):
        """Commit and log progress."""
        self.pg.commit()
        log.info(f"{label} progress", processed=count, total=total, **dict(self.stats))

    def close(self):
        self.pg.close()
