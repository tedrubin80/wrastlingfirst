"""Load transformed data into PostgreSQL with upsert logic."""

import json
from datetime import date
from pathlib import Path

import psycopg2
import psycopg2.extensions
import structlog

from etl.entity_resolution import EntityResolver

logger = structlog.get_logger(__name__)


class DataLoader:
    """Loads scraped event/match JSON into the database."""

    def __init__(self, conn: psycopg2.extensions.connection):
        self.conn = conn
        self.resolver = EntityResolver(conn)
        self.stats = {
            "events_loaded": 0,
            "events_skipped": 0,
            "matches_loaded": 0,
            "participants_loaded": 0,
            "unresolved_names": 0,
        }

    def load_file(self, path: Path) -> None:
        """Load events from a JSON file."""
        logger.info("loading_file", path=str(path))
        data = json.loads(path.read_text(encoding="utf-8"))

        for event_data in data:
            try:
                self._load_event(event_data)
            except Exception:
                logger.exception(
                    "event_load_failed",
                    event_name=event_data.get("name"),
                )
                self.conn.rollback()

        self.stats["unresolved_names"] = len(self.resolver.unresolved)
        logger.info("file_loaded", path=str(path), stats=self.stats)

    def _get_promotion_id(self, promotion: str | None) -> int | None:
        """Look up promotion ID by abbreviation."""
        if not promotion:
            return None
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM promotions WHERE abbreviation = %s",
                (promotion.upper(),),
            )
            row = cur.fetchone()
            return row[0] if row else None

    def _load_event(self, data: dict) -> None:
        """Insert or update a single event and its matches."""
        promotion_id = self._get_promotion_id(data.get("promotion"))
        if not promotion_id:
            logger.warning("unknown_promotion_in_data", promotion=data.get("promotion"))
            self.stats["events_skipped"] += 1
            return

        event_date = data.get("date")
        if isinstance(event_date, str):
            event_date = date.fromisoformat(event_date)

        with self.conn.cursor() as cur:
            # Upsert event
            cur.execute(
                """
                INSERT INTO events
                    (name, promotion_id, date, venue, city, state, country,
                     event_type, cagematch_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (cagematch_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    venue = EXCLUDED.venue,
                    city = EXCLUDED.city,
                    updated_at = now()
                RETURNING id
                """,
                (
                    data.get("name"),
                    promotion_id,
                    event_date,
                    data.get("venue"),
                    data.get("city"),
                    data.get("state"),
                    data.get("country"),
                    data.get("event_type", "weekly_tv"),
                    data.get("cagematch_id"),
                ),
            )
            event_id = cur.fetchone()[0]

        self.stats["events_loaded"] += 1

        # Load matches
        for match_data in data.get("matches", []):
            self._load_match(event_id, match_data)

        self.conn.commit()

    def _load_match(self, event_id: int, data: dict) -> None:
        """Insert a single match and its participants."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO matches
                    (event_id, match_order, match_type, stipulation,
                     duration_seconds, title_match, rating)
                VALUES (%s, %s, %s::match_type, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    event_id,
                    data.get("match_order"),
                    data.get("match_type", "other"),
                    data.get("stipulation"),
                    data.get("duration_seconds"),
                    data.get("title_match", False),
                    data.get("rating"),
                ),
            )
            match_id = cur.fetchone()[0]

        self.stats["matches_loaded"] += 1

        # Load participants
        for p in data.get("participants", []):
            resolved = self.resolver.resolve(p.get("name", ""))
            if not resolved:
                continue

            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO match_participants
                        (match_id, wrestler_id, team_number, result,
                         entry_order, elimination_order)
                    VALUES (%s, %s, %s, %s::match_result, %s, %s)
                    ON CONFLICT (match_id, wrestler_id) DO NOTHING
                    """,
                    (
                        match_id,
                        resolved.wrestler_id,
                        p.get("team_number"),
                        p.get("result", "loss"),
                        p.get("entry_order"),
                        p.get("elimination_order"),
                    ),
                )

            self.stats["participants_loaded"] += 1

    def get_unresolved_names(self) -> list[str]:
        """Return list of wrestler names that could not be resolved."""
        return sorted(set(self.resolver.unresolved))
