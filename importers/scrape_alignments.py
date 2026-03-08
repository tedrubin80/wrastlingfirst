"""
Scrape wrestler alignment (face/heel/tweener) data from:
1. SmackDown Hotel — current roster snapshot + yearly turn history
2. Smark Out Moment — yearly turn history (complementary)

Usage:
    python -m importers.scrape_alignments
    python -m importers.scrape_alignments --years 2020,2021,2022,2023,2024,2025,2026
"""

import argparse
import os
import re
import time
from collections import defaultdict
from datetime import datetime
from typing import Optional

import psycopg2
import requests
from bs4 import BeautifulSoup
import structlog

from .shared import BaseImporter

log = structlog.get_logger()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RingsideAnalytics/1.0; research)"
}
RATE_LIMIT = 1.5  # seconds between requests


def fetch_page(url: str) -> Optional[BeautifulSoup]:
    """Fetch and parse a page with rate limiting."""
    time.sleep(RATE_LIMIT)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        log.warning("Failed to fetch page", url=url, error=str(e))
        return None


# ---------------------------------------------------------------------------
# SmackDown Hotel: Current face/heel roster snapshot
# ---------------------------------------------------------------------------

def scrape_sdh_roster(imp: BaseImporter) -> dict[str, int]:
    """Scrape SmackDown Hotel face/heel roster page."""
    stats: dict[str, int] = defaultdict(int)
    url = "https://www.thesmackdownhotel.com/roster/?promotion=wwe&show=face-heel"
    log.info("Scraping SmackDown Hotel roster", url=url)

    soup = fetch_page(url)
    if not soup:
        log.error("Failed to fetch SDH roster page")
        return dict(stats)

    today = datetime.now().strftime("%Y-%m-%d")
    current_alignment = None

    # The page uses h2/h3 headers to separate Face/Heel/Tweener sections
    # and wrestler links within each section
    for element in soup.find_all(["h2", "h3", "h4", "a"]):
        text = element.get_text(strip=True).lower()

        # Detect alignment section headers
        if element.name in ("h2", "h3", "h4"):
            if "face" in text and "heel" not in text:
                current_alignment = "face"
            elif "heel" in text and "face" not in text:
                current_alignment = "heel"
            elif "tweener" in text:
                current_alignment = "tweener"

        # Wrestler links within alignment sections
        if element.name == "a" and current_alignment:
            href = element.get("href", "")
            if "/wrestlers/" in href:
                wrestler_name = element.get_text(strip=True)
                if not wrestler_name:
                    continue

                key = wrestler_name.lower().strip()
                if key in imp._wrestler_cache:
                    wid = imp._wrestler_cache[key]
                    with imp.pg.cursor() as cur:
                        cur.execute(
                            """INSERT INTO wrestler_alignments
                               (wrestler_id, alignment, effective_date, source)
                               VALUES (%s, %s, %s, 'smackdown_hotel')
                               ON CONFLICT (wrestler_id, effective_date) DO UPDATE
                               SET alignment = EXCLUDED.alignment""",
                            (wid, current_alignment, today),
                        )
                    stats["alignments_set"] += 1
                else:
                    stats["wrestlers_not_found"] += 1

    imp.pg.commit()
    log.info("SDH roster scrape done", **dict(stats))
    return dict(stats)


# ---------------------------------------------------------------------------
# SmackDown Hotel: Yearly turn history
# ---------------------------------------------------------------------------

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9,
    "oct": 10, "nov": 11, "dec": 12,
}


def parse_turn_date(text: str, year: int) -> Optional[str]:
    """Parse date strings like 'January 15, 2024' or 'Jan 15' → 'YYYY-MM-DD'."""
    # Try full date: "Month DD, YYYY"
    m = re.search(r'(\w+)\s+(\d{1,2}),?\s*(\d{4})?', text)
    if m:
        month_str = m.group(1).lower()
        day = int(m.group(2))
        yr = int(m.group(3)) if m.group(3) else year
        month = MONTH_MAP.get(month_str)
        if month:
            return f"{yr:04d}-{month:02d}-{day:02d}"
    return None


def scrape_sdh_turns(imp: BaseImporter, year: int) -> dict[str, int]:
    """Scrape SmackDown Hotel turn history for a given year."""
    stats: dict[str, int] = defaultdict(int)
    url = f"https://www.thesmackdownhotel.com/roster/wwe-face-heel-turns-list?year={year}"
    log.info("Scraping SDH turns", year=year, url=url)

    soup = fetch_page(url)
    if not soup:
        return dict(stats)

    # Find all wrestler entries — each turn has a wrestler name in an h3/a tag
    # followed by turn direction and date info
    entries = soup.find_all("div", class_=re.compile(r"turn|entry|item|wrestler", re.I))

    if not entries:
        # Fallback: look for structured content in the main content area
        content = soup.find("div", {"id": "content"}) or soup.find("main") or soup
        # Parse all text blocks looking for turn patterns
        text_blocks = content.get_text(separator="\n").split("\n")
        _parse_turn_text_blocks(imp, text_blocks, year, stats)
    else:
        for entry in entries:
            _parse_turn_entry(imp, entry, year, stats)

    imp.pg.commit()
    log.info("SDH turns scrape done", year=year, **dict(stats))
    return dict(stats)


def _parse_turn_entry(imp: BaseImporter, entry, year: int, stats: dict):
    """Parse a single turn entry div."""
    text = entry.get_text(separator=" ").strip()

    # Find wrestler name (usually in a link)
    name_link = entry.find("a", href=re.compile(r"/wrestlers/"))
    wrestler_name = name_link.get_text(strip=True) if name_link else None

    if not wrestler_name:
        stats["skipped_no_name"] += 1
        return

    # Determine turn direction
    text_lower = text.lower()
    if "heel turn" in text_lower:
        to_alignment = "heel"
        from_alignment = "face"
    elif "face turn" in text_lower or "babyface turn" in text_lower:
        to_alignment = "face"
        from_alignment = "heel"
    elif "tweener" in text_lower:
        to_alignment = "tweener"
        from_alignment = "heel"  # best guess
    else:
        stats["skipped_no_direction"] += 1
        return

    # Parse date
    turn_date = parse_turn_date(text, year)
    if not turn_date:
        turn_date = f"{year}-01-01"  # fallback

    # Find wrestler in our DB
    key = wrestler_name.lower().strip()
    if key not in imp._wrestler_cache:
        stats["wrestlers_not_found"] += 1
        return

    wid = imp._wrestler_cache[key]

    # Extract description (the full text minus the name)
    description = text[:200] if text else None

    with imp.pg.cursor() as cur:
        cur.execute(
            """INSERT INTO alignment_turns
               (wrestler_id, from_alignment, to_alignment, turn_date, description, source)
               VALUES (%s, %s, %s, %s, %s, 'smackdown_hotel')
               ON CONFLICT DO NOTHING""",
            (wid, from_alignment, to_alignment, turn_date, description),
        )
        if cur.rowcount > 0:
            stats["turns_added"] += 1
        else:
            stats["turns_duplicate"] += 1

        # Also set alignment snapshot
        cur.execute(
            """INSERT INTO wrestler_alignments
               (wrestler_id, alignment, effective_date, source)
               VALUES (%s, %s, %s, 'smackdown_hotel')
               ON CONFLICT (wrestler_id, effective_date) DO UPDATE
               SET alignment = EXCLUDED.alignment""",
            (wid, to_alignment, turn_date),
        )


def _parse_turn_text_blocks(imp: BaseImporter, blocks: list[str], year: int, stats: dict):
    """Fallback: parse turn info from raw text blocks."""
    current_wrestler = None
    current_direction = None

    for line in blocks:
        line = line.strip()
        if not line:
            continue

        line_lower = line.lower()

        # Detect turn direction
        if "heel turn" in line_lower:
            current_direction = ("face", "heel")
        elif "face turn" in line_lower or "babyface turn" in line_lower:
            current_direction = ("heel", "face")
        elif "tweener turn" in line_lower:
            current_direction = ("heel", "tweener")

        # Try to find a date in the line
        turn_date = parse_turn_date(line, year)

        # Try to find a wrestler name (capitalized words that match our DB)
        # Look for known wrestler names
        words = re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', line)
        for potential_name in words:
            key = potential_name.lower().strip()
            if key in imp._wrestler_cache and len(key) > 3:
                current_wrestler = key
                break

        # If we have all pieces, record the turn
        if current_wrestler and current_direction and turn_date:
            wid = imp._wrestler_cache[current_wrestler]
            from_a, to_a = current_direction

            with imp.pg.cursor() as cur:
                cur.execute(
                    """INSERT INTO alignment_turns
                       (wrestler_id, from_alignment, to_alignment, turn_date,
                        description, source)
                       VALUES (%s, %s, %s, %s, %s, 'smackdown_hotel')
                       ON CONFLICT DO NOTHING""",
                    (wid, from_a, to_a, turn_date, line[:200]),
                )
                if cur.rowcount > 0:
                    stats["turns_added"] += 1

                cur.execute(
                    """INSERT INTO wrestler_alignments
                       (wrestler_id, alignment, effective_date, source)
                       VALUES (%s, %s, %s, 'smackdown_hotel')
                       ON CONFLICT (wrestler_id, effective_date) DO UPDATE
                       SET alignment = EXCLUDED.alignment""",
                    (wid, to_a, turn_date),
                )

            # Reset for next turn
            current_wrestler = None
            current_direction = None


# ---------------------------------------------------------------------------
# Smark Out Moment: Yearly turn history
# ---------------------------------------------------------------------------

def scrape_som_turns(imp: BaseImporter, year: int) -> dict[str, int]:
    """Scrape Smark Out Moment turn history for a given year."""
    stats: dict[str, int] = defaultdict(int)
    url = f"https://www.smarkoutmoment.com/{year}/01/wwe-heel-face-turns-{year}-list.html"
    log.info("Scraping Smark Out Moment turns", year=year, url=url)

    soup = fetch_page(url)
    if not soup:
        return dict(stats)

    # SOM typically uses blog post format with entries in the post body
    content = soup.find("div", class_="post-body") or soup.find("div", class_="entry") or soup
    text_blocks = content.get_text(separator="\n").split("\n")

    current_direction = None
    for line in text_blocks:
        line = line.strip()
        if not line or len(line) < 5:
            continue

        line_lower = line.lower()

        # Detect turn direction
        if "heel turn" in line_lower:
            current_direction = ("face", "heel")
        elif "face turn" in line_lower or "babyface turn" in line_lower:
            current_direction = ("heel", "face")

        # Try to parse date
        turn_date = parse_turn_date(line, year)

        # Look for wrestler names we know
        matched_wrestler = None
        for name_key, wid in imp._wrestler_cache.items():
            if len(name_key) > 4 and name_key in line.lower():
                matched_wrestler = (name_key, wid)
                break

        if matched_wrestler and current_direction and turn_date:
            name_key, wid = matched_wrestler
            from_a, to_a = current_direction

            with imp.pg.cursor() as cur:
                cur.execute(
                    """INSERT INTO alignment_turns
                       (wrestler_id, from_alignment, to_alignment, turn_date,
                        description, source)
                       VALUES (%s, %s, %s, %s, %s, 'smark_out_moment')
                       ON CONFLICT DO NOTHING""",
                    (wid, from_a, to_a, turn_date, line[:200]),
                )
                if cur.rowcount > 0:
                    stats["turns_added"] += 1

                cur.execute(
                    """INSERT INTO wrestler_alignments
                       (wrestler_id, alignment, effective_date, source)
                       VALUES (%s, %s, %s, 'smark_out_moment')
                       ON CONFLICT (wrestler_id, effective_date) DO UPDATE
                       SET alignment = EXCLUDED.alignment""",
                    (wid, to_a, turn_date),
                )

            current_direction = None

    imp.pg.commit()
    log.info("SOM turns scrape done", year=year, **dict(stats))
    return dict(stats)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(pg_dsn: str, years: Optional[list[int]] = None):
    """Run all alignment scrapers."""
    if years is None:
        years = list(range(2020, 2027))

    imp = BaseImporter(pg_dsn)
    imp.load_caches()

    all_stats: dict[str, dict] = {}

    # 1. Current roster snapshot from SmackDown Hotel
    all_stats["sdh_roster"] = scrape_sdh_roster(imp)

    # 2. Turn history from SmackDown Hotel (per year)
    for year in years:
        key = f"sdh_turns_{year}"
        all_stats[key] = scrape_sdh_turns(imp, year)

    # 3. Turn history from Smark Out Moment (per year)
    for year in years:
        key = f"som_turns_{year}"
        all_stats[key] = scrape_som_turns(imp, year)

    imp.close()

    # Summary
    total_alignments = sum(s.get("alignments_set", 0) for s in all_stats.values())
    total_turns = sum(s.get("turns_added", 0) for s in all_stats.values())
    log.info("Alignment scrape complete",
             total_alignments=total_alignments,
             total_turns=total_turns,
             sources=len(all_stats))

    return all_stats


def main():
    parser = argparse.ArgumentParser(description="Scrape alignment data")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", "postgresql://ringside:ringside@localhost:5432/ringside"),
    )
    parser.add_argument(
        "--years",
        default="2020,2021,2022,2023,2024,2025,2026",
        help="Comma-separated years to scrape turns for",
    )
    args = parser.parse_args()
    years = [int(y) for y in args.years.split(",")]
    run(args.database_url, years)


if __name__ == "__main__":
    main()
