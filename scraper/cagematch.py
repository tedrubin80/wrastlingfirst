"""Main scraper orchestrator for Cagematch.net."""

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

import structlog

from scraper.config import BASE_URL, PROMOTION_IDS, ScrapeConfig
from scraper.http_client import HttpClient
from scraper.parser import parse_event_list_page, parse_event_page, ParsedEvent

logger = structlog.get_logger(__name__)


class CagematchScraper:
    """Scrapes event and match data from Cagematch.net."""

    def __init__(self, config: ScrapeConfig):
        self.config = config
        self.client = HttpClient(
            rate_limit=config.rate_limit,
            max_retries=config.max_retries,
            cache_dir=config.cache_dir,
        )
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

    def _event_list_url(self, promotion_id: int, year: int, page: int = 0) -> str:
        """Build URL for a promotion's event list page.

        Cagematch distinguishes view=search (the form page) from view=results
        (the actual event listing). The old URL used view=search, which returns
        the empty form and no TableContents — causing the parser to return 0
        events and the pagination loop to break immediately (or, when garbage
        stubs got returned, loop forever).
        """
        return (
            f"{BASE_URL}/?id=1&view=results&sPromotion={promotion_id}"
            f"&sDateFromDay=01&sDateFromMonth=01&sDateFromYear={year}"
            f"&sDateTillDay=31&sDateTillMonth=12&sDateTillYear={year}"
            f"&s={page * 100}"
        )

    def _event_detail_url(self, cagematch_id: str) -> str:
        """Build URL for an event detail page.

        page=1 is the full match-results view (contains "defeats" text).
        page=2 is a lighter card preview that omits results. We want page=1.
        """
        return f"{BASE_URL}/?id=1&nr={cagematch_id}&page=1"

    def scrape_promotion_year(self, promotion: str, year: int) -> list[ParsedEvent]:
        """Scrape all events for a promotion in a given year."""
        promo_id = PROMOTION_IDS.get(promotion)
        if promo_id is None:
            logger.error("unknown_promotion", promotion=promotion)
            return []

        logger.info("scraping_year", promotion=promotion, year=year)
        all_events: list[ParsedEvent] = []
        seen_ids: set[str] = set()

        # Cagematch's s= offset doesn't return empty when over-paginated — it
        # echoes back stale stubs, causing infinite loops. Guard with a
        # dedup-on-id check AND a hard page cap (real promo-years top out ~30).
        MAX_PAGES = 200
        page = 0
        while page < MAX_PAGES:
            url = self._event_list_url(promo_id, year, page)
            # Bypass cache for event-list pages: new events are added over time,
            # so stale list pages would hide them. Detail pages (below) are
            # safe to cache since they're immutable once published.
            html = self.client.get(url, use_cache=False)
            event_stubs = parse_event_list_page(html)

            if not event_stubs:
                break

            new_stubs = [
                s for s in event_stubs
                if s.get("cagematch_id") and s["cagematch_id"] not in seen_ids
            ]
            if not new_stubs:
                logger.info(
                    "event_list_exhausted",
                    promotion=promotion,
                    year=year,
                    page=page,
                    reason="no_new_ids",
                )
                break

            logger.info(
                "event_list_page",
                promotion=promotion,
                year=year,
                page=page,
                events_found=len(event_stubs),
                new_events=len(new_stubs),
            )

            for stub in new_stubs:
                seen_ids.add(stub["cagematch_id"])
                try:
                    detail_url = self._event_detail_url(stub["cagematch_id"])
                    detail_html = self.client.get(detail_url)
                    event = parse_event_page(detail_html, stub)
                    event.promotion = promotion

                    all_events.append(event)
                    # Note: structlog reserves `event` as the positional
                    # message arg, so we must use `event_name` as the kwarg.
                    logger.info(
                        "event_scraped",
                        event_name=event.name,
                        date=str(event.date),
                        matches=len(event.matches),
                    )
                except Exception:
                    logger.exception(
                        "event_scrape_failed",
                        cagematch_id=stub.get("cagematch_id"),
                        event_name=stub.get("name"),
                    )

            page += 1

        if page >= MAX_PAGES:
            logger.warning(
                "event_list_page_cap_hit",
                promotion=promotion,
                year=year,
                max_pages=MAX_PAGES,
            )

        return all_events

    def scrape_all(self) -> list[ParsedEvent]:
        """Run the full scrape across all configured promotions and years."""
        all_events: list[ParsedEvent] = []

        for promotion in self.config.promotions:
            for year in range(self.config.year_start, self.config.year_end + 1):
                events = self.scrape_promotion_year(promotion, year)
                all_events.extend(events)

                # Write per-promotion-year output
                output_file = (
                    self.config.output_dir
                    / f"{promotion.lower()}_{year}.json"
                )
                self._write_events(events, output_file)

        # Write combined output
        combined_file = self.config.output_dir / "all_events.json"
        self._write_events(all_events, combined_file)

        logger.info(
            "scrape_complete",
            total_events=len(all_events),
            total_matches=sum(len(e.matches) for e in all_events),
        )

        return all_events

    def _write_events(self, events: list[ParsedEvent], path: Path) -> None:
        """Serialize events to JSON, converting dates to strings."""
        def serialize(obj):
            if isinstance(obj, date):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        data = [asdict(e) for e in events]
        path.write_text(
            json.dumps(data, indent=2, default=serialize),
            encoding="utf-8",
        )
        logger.info("output_written", path=str(path), events=len(events))
