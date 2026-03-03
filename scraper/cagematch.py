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
        """Build URL for a promotion's event list page."""
        return (
            f"{BASE_URL}/?id=1&view=search&sPromotion={promotion_id}"
            f"&sDateFromDay=01&sDateFromMonth=01&sDateFromYear={year}"
            f"&sDateTillDay=31&sDateTillMonth=12&sDateTillYear={year}"
            f"&s={page * 100}"
        )

    def _event_detail_url(self, cagematch_id: str) -> str:
        """Build URL for an event detail page."""
        return f"{BASE_URL}/?id=1&nr={cagematch_id}&page=2"

    def scrape_promotion_year(self, promotion: str, year: int) -> list[ParsedEvent]:
        """Scrape all events for a promotion in a given year."""
        promo_id = PROMOTION_IDS.get(promotion)
        if promo_id is None:
            logger.error("unknown_promotion", promotion=promotion)
            return []

        logger.info("scraping_year", promotion=promotion, year=year)
        all_events: list[ParsedEvent] = []

        page = 0
        while True:
            url = self._event_list_url(promo_id, year, page)
            html = self.client.get(url)
            event_stubs = parse_event_list_page(html)

            if not event_stubs:
                break

            logger.info(
                "event_list_page",
                promotion=promotion,
                year=year,
                page=page,
                events_found=len(event_stubs),
            )

            for stub in event_stubs:
                if not stub.get("cagematch_id"):
                    continue

                try:
                    detail_url = self._event_detail_url(stub["cagematch_id"])
                    detail_html = self.client.get(detail_url)
                    event = parse_event_page(detail_html, stub)
                    event.promotion = promotion

                    all_events.append(event)
                    logger.info(
                        "event_scraped",
                        event=event.name,
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
