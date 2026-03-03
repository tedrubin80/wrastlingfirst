"""CLI entry point for the Cagematch scraper."""

import argparse
import sys

import structlog

from scraper.cagematch import CagematchScraper
from scraper.config import PROMOTION_IDS, ScrapeConfig

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)

logger = structlog.get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Scrape wrestling match data from Cagematch.net"
    )
    parser.add_argument(
        "--promotions",
        nargs="+",
        default=["WWE", "AEW"],
        choices=list(PROMOTION_IDS.keys()),
        help="Promotions to scrape",
    )
    parser.add_argument(
        "--year-start",
        type=int,
        default=2020,
        help="Start year (default: 2020)",
    )
    parser.add_argument(
        "--year-end",
        type=int,
        default=2026,
        help="End year (default: 2026)",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=1.0,
        help="Seconds between requests (default: 1.0)",
    )
    parser.add_argument(
        "--output-dir",
        default="./output",
        help="Directory for JSON output files",
    )
    parser.add_argument(
        "--cache-dir",
        default="./cache",
        help="Directory for cached HTML files",
    )

    args = parser.parse_args()

    config = ScrapeConfig(
        promotions=args.promotions,
        year_start=args.year_start,
        year_end=args.year_end,
        rate_limit=args.rate_limit,
        output_dir=args.output_dir,
        cache_dir=args.cache_dir,
    )

    logger.info("scraper_starting", config=vars(config))

    scraper = CagematchScraper(config)
    events = scraper.scrape_all()

    total_matches = sum(len(e.matches) for e in events)
    logger.info(
        "scraper_finished",
        events=len(events),
        matches=total_matches,
    )

    print(f"\nDone: {len(events)} events, {total_matches} matches scraped.")


if __name__ == "__main__":
    main()
