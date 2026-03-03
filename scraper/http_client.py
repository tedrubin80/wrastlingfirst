"""Rate-limited HTTP client with caching and exponential backoff."""

import hashlib
import time
from pathlib import Path

import requests
import structlog

from scraper.config import BACKOFF_BASE, USER_AGENT

logger = structlog.get_logger(__name__)


class HttpClient:
    """HTTP client with rate limiting, retries, and local HTML cache."""

    def __init__(
        self,
        rate_limit: float = 1.0,
        max_retries: int = 3,
        cache_dir: Path | None = None,
    ):
        self.rate_limit = rate_limit
        self.max_retries = max_retries
        self.cache_dir = cache_dir
        self._last_request_time: float = 0.0

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        })

        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()

    def _cache_path(self, url: str) -> Path | None:
        if not self.cache_dir:
            return None
        return self.cache_dir / f"{self._cache_key(url)}.html"

    def _read_cache(self, url: str) -> str | None:
        path = self._cache_path(url)
        if path and path.exists():
            logger.debug("cache_hit", url=url)
            return path.read_text(encoding="utf-8")
        return None

    def _write_cache(self, url: str, content: str) -> None:
        path = self._cache_path(url)
        if path:
            path.write_text(content, encoding="utf-8")

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_time
        wait = self.rate_limit - elapsed
        if wait > 0:
            time.sleep(wait)

    def get(self, url: str, use_cache: bool = True) -> str:
        """Fetch a URL with rate limiting, caching, and retries."""
        if use_cache:
            cached = self._read_cache(url)
            if cached is not None:
                return cached

        for attempt in range(1, self.max_retries + 1):
            try:
                self._throttle()
                self._last_request_time = time.monotonic()

                logger.info("http_request", url=url, attempt=attempt)
                response = self.session.get(url, timeout=30)
                response.raise_for_status()

                html = response.text
                self._write_cache(url, html)
                return html

            except requests.exceptions.HTTPError as e:
                if response.status_code == 429 or response.status_code >= 500:
                    wait = BACKOFF_BASE ** attempt
                    logger.warning(
                        "http_retry",
                        url=url,
                        status=response.status_code,
                        wait=wait,
                        attempt=attempt,
                    )
                    time.sleep(wait)
                    continue
                logger.error("http_error", url=url, status=response.status_code)
                raise

            except requests.exceptions.RequestException as e:
                wait = BACKOFF_BASE ** attempt
                logger.warning(
                    "http_retry",
                    url=url,
                    error=str(e),
                    wait=wait,
                    attempt=attempt,
                )
                time.sleep(wait)

        raise RuntimeError(f"Failed to fetch {url} after {self.max_retries} retries")
