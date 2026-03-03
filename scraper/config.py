"""Scraper configuration — promotion IDs, URLs, rate limits."""

import os
from dataclasses import dataclass, field
from pathlib import Path


BASE_URL = "https://www.cagematch.net"

# Cagematch promotion IDs
PROMOTION_IDS = {
    "WWE": 1,
    "AEW": 27,
    "WCW": 2,
    "ECW": 3,
    "TNA": 5,
    "NXT": 29,
    "ROH": 9,
}

# Rate limiting
DEFAULT_RATE_LIMIT = float(os.environ.get("SCRAPER_RATE_LIMIT", "1.0"))
MAX_RETRIES = 3
BACKOFF_BASE = 2.0

# Cache
DEFAULT_CACHE_DIR = Path(os.environ.get("SCRAPER_CACHE_DIR", "./cache"))

# User agent
USER_AGENT = (
    "RingsideAnalytics/1.0 "
    "(wrestling research project; respects robots.txt; 1 req/sec)"
)


@dataclass
class ScrapeConfig:
    """Configuration for a scraping run."""
    promotions: list[str] = field(default_factory=lambda: ["WWE", "AEW"])
    year_start: int = 2020
    year_end: int = 2026
    rate_limit: float = DEFAULT_RATE_LIMIT
    cache_dir: Path = DEFAULT_CACHE_DIR
    max_retries: int = MAX_RETRIES
    output_dir: Path = Path("./output")
