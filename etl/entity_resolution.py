"""Fuzzy name matching for wrestler entity resolution."""

from dataclasses import dataclass

import psycopg2.extensions
from rapidfuzz import fuzz, process
import structlog

logger = structlog.get_logger(__name__)

MATCH_THRESHOLD = 85  # Minimum fuzzy match score to auto-link


@dataclass
class ResolvedWrestler:
    wrestler_id: int
    ring_name: str
    score: float
    exact: bool


class EntityResolver:
    """Resolves scraped wrestler names to database wrestler IDs using fuzzy matching."""

    def __init__(self, conn: psycopg2.extensions.connection):
        self.conn = conn
        self._alias_cache: dict[str, int] = {}
        self._name_choices: list[str] = []
        self._name_to_id: dict[str, int] = {}
        self.unresolved: list[str] = []
        self._load_aliases()

    def _load_aliases(self) -> None:
        """Load all wrestler names and aliases into memory for matching."""
        with self.conn.cursor() as cur:
            # Load primary names
            cur.execute("SELECT id, ring_name FROM wrestlers")
            for wid, name in cur.fetchall():
                lower = name.lower().strip()
                self._alias_cache[lower] = wid
                self._name_to_id[name] = wid
                self._name_choices.append(name)

            # Load aliases
            cur.execute("SELECT wrestler_id, alias FROM wrestler_aliases")
            for wid, alias in cur.fetchall():
                lower = alias.lower().strip()
                if lower not in self._alias_cache:
                    self._alias_cache[lower] = wid
                    self._name_to_id[alias] = wid
                    self._name_choices.append(alias)

        logger.info("aliases_loaded", count=len(self._alias_cache))

    def resolve(self, name: str) -> ResolvedWrestler | None:
        """Resolve a wrestler name to a database ID."""
        if not name or not name.strip():
            return None

        clean = name.strip()
        lower = clean.lower()

        # Exact match
        if lower in self._alias_cache:
            return ResolvedWrestler(
                wrestler_id=self._alias_cache[lower],
                ring_name=clean,
                score=100.0,
                exact=True,
            )

        # Fuzzy match
        if not self._name_choices:
            self.unresolved.append(clean)
            return None

        result = process.extractOne(
            clean,
            self._name_choices,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=MATCH_THRESHOLD,
        )

        if result:
            matched_name, score, _ = result
            wrestler_id = self._name_to_id[matched_name]
            logger.debug(
                "fuzzy_match",
                input=clean,
                matched=matched_name,
                score=score,
            )

            # Auto-add this as a new alias for future lookups
            self._alias_cache[lower] = wrestler_id
            self._add_alias(wrestler_id, clean)

            return ResolvedWrestler(
                wrestler_id=wrestler_id,
                ring_name=matched_name,
                score=score,
                exact=False,
            )

        logger.warning("unresolved_wrestler", name=clean)
        self.unresolved.append(clean)
        return None

    def _add_alias(self, wrestler_id: int, alias: str) -> None:
        """Insert a newly discovered alias into the database."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO wrestler_aliases (wrestler_id, alias)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (wrestler_id, alias),
                )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            logger.exception("alias_insert_failed", wrestler_id=wrestler_id, alias=alias)
