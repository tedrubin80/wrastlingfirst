"""HTML parsers for Cagematch.net event and match pages."""

import re
from dataclasses import dataclass, field
from datetime import date

from bs4 import BeautifulSoup, Tag
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ParsedParticipant:
    name: str
    result: str  # win, loss, draw, no_contest, dq, countout
    team_number: int | None = None
    entry_order: int | None = None
    elimination_order: int | None = None


@dataclass
class ParsedMatch:
    match_order: int
    match_type: str
    stipulation: str | None = None
    duration_seconds: int | None = None
    title_match: bool = False
    rating: float | None = None
    participants: list[ParsedParticipant] = field(default_factory=list)


@dataclass
class ParsedEvent:
    name: str
    date: date | None = None
    venue: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    event_type: str = "weekly_tv"
    promotion: str | None = None
    cagematch_id: str | None = None
    matches: list[ParsedMatch] = field(default_factory=list)


# Match type keyword mapping to our ENUMs
MATCH_TYPE_MAP = {
    "singles": "singles",
    "single": "singles",
    "1 vs. 1": "singles",
    "tag team": "tag_team",
    "tag": "tag_team",
    "triple threat": "triple_threat",
    "three way": "triple_threat",
    "3-way": "triple_threat",
    "fatal four": "fatal_four_way",
    "fatal 4": "fatal_four_way",
    "four way": "fatal_four_way",
    "4-way": "fatal_four_way",
    "battle royal": "battle_royal",
    "battle royale": "battle_royal",
    "royal rumble": "royal_rumble",
    "rumble": "royal_rumble",
    "ladder": "ladder",
    "money in the bank": "ladder",
    "tlc": "tlc",
    "tables ladders": "tlc",
    "hell in a cell": "hell_in_a_cell",
    "hiac": "hell_in_a_cell",
    "steel cage": "cage",
    "cage match": "cage",
    "cage": "cage",
    "elimination chamber": "elimination_chamber",
    "war games": "elimination_chamber",
    "iron man": "iron_man",
    "ironman": "iron_man",
    "i quit": "i_quit",
    "last man standing": "last_man_standing",
    "tables match": "tables",
    "tables": "tables",
    "handicap": "handicap",
    "gauntlet": "gauntlet",
}


def classify_match_type(text: str) -> str:
    """Map a match type description to our ENUM value."""
    lower = text.lower().strip()
    for keyword, enum_val in MATCH_TYPE_MAP.items():
        if keyword in lower:
            return enum_val
    return "other"


def parse_duration(text: str) -> int | None:
    """Parse duration string like '12:34' into total seconds."""
    match = re.search(r"(\d+):(\d+)", text)
    if match:
        minutes, seconds = int(match.group(1)), int(match.group(2))
        return minutes * 60 + seconds
    return None


def classify_event_type(name: str) -> str:
    """Infer event type from name."""
    lower = name.lower()
    ppv_keywords = [
        "wrestlemania", "summerslam", "royal rumble", "survivor series",
        "money in the bank", "elimination chamber", "hell in a cell",
        "tlc", "payback", "backlash", "fastlane", "clash of champions",
        "extreme rules", "night of champions", "all out", "revolution",
        "double or nothing", "full gear", "dynasty", "all in",
        "forbidden door", "worlds end", "grand slam",
        "takeover", "stand & deliver", "halloween havoc",
        "battleground", "no mercy", "vengeance",
    ]
    if any(kw in lower for kw in ppv_keywords):
        return "ppv"
    tv_keywords = ["raw", "smackdown", "dynamite", "rampage", "collision",
                   "nitro", "thunder", "nxt tv", "dark", "elevation"]
    if any(kw in lower for kw in tv_keywords):
        return "weekly_tv"
    if "special" in lower or "supershow" in lower:
        return "special"
    if "house show" in lower or "live event" in lower:
        return "house_show"
    if "tournament" in lower or "king of the ring" in lower:
        return "tournament"
    return "weekly_tv"


def parse_event_list_page(html: str) -> list[dict]:
    """Parse a Cagematch event list page, return list of event stubs with URLs."""
    soup = BeautifulSoup(html, "lxml")
    events = []

    table = soup.find("div", class_="TableContents")
    if not table:
        return events

    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue

        link = cells[1].find("a") if len(cells) > 1 else None
        if not link:
            continue

        href = link.get("href", "")
        event_name = link.get_text(strip=True)

        date_text = cells[0].get_text(strip=True) if cells else ""
        event_date = None
        date_match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", date_text)
        if date_match:
            day, month, year = date_match.groups()
            try:
                event_date = date(int(year), int(month), int(day))
            except ValueError:
                pass

        # Extract cagematch ID from URL
        cm_id = None
        id_match = re.search(r"nr=(\d+)", href)
        if id_match:
            cm_id = id_match.group(1)

        events.append({
            "name": event_name,
            "date": event_date,
            "url": href,
            "cagematch_id": cm_id,
        })

    return events


def parse_event_page(html: str, event_stub: dict | None = None) -> ParsedEvent:
    """Parse a full Cagematch event page into a ParsedEvent with matches."""
    soup = BeautifulSoup(html, "lxml")

    name = ""
    event_date = None
    venue = None
    city = None
    country = None

    # Parse event info from the information block
    info_box = soup.find("div", class_="InformationBoxTable")
    if info_box:
        for row in info_box.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            label = cells[0].get_text(strip=True).lower()
            value = cells[1].get_text(strip=True)

            if "name" in label or "event" in label:
                name = value
            elif "date" in label:
                dm = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", value)
                if dm:
                    try:
                        event_date = date(int(dm.group(3)), int(dm.group(2)), int(dm.group(1)))
                    except ValueError:
                        pass
            elif "arena" in label or "venue" in label or "location" in label:
                venue = value
                # Try to split "Venue, City, Country"
                parts = [p.strip() for p in value.split(",")]
                if len(parts) >= 3:
                    venue = parts[0]
                    city = parts[1]
                    country = parts[-1]
                elif len(parts) == 2:
                    venue = parts[0]
                    city = parts[1]

    # Use stub data as fallback
    if event_stub:
        name = name or event_stub.get("name", "")
        event_date = event_date or event_stub.get("date")

    event = ParsedEvent(
        name=name,
        date=event_date,
        venue=venue,
        city=city,
        country=country,
        event_type=classify_event_type(name),
        cagematch_id=event_stub.get("cagematch_id") if event_stub else None,
    )

    # Parse match card
    match_card = soup.find("div", class_="Matchcard")
    if not match_card:
        # Try alternative selectors
        match_card = soup.find("div", class_="MatchCard")

    if match_card:
        match_divs = match_card.find_all("div", class_="MatchCard")
        if not match_divs:
            match_divs = match_card.find_all("div", recursive=False)

        for i, match_div in enumerate(match_divs, 1):
            parsed_match = _parse_match_div(match_div, i)
            if parsed_match and parsed_match.participants:
                event.matches.append(parsed_match)

    return event


def _parse_match_div(div: Tag, order: int) -> ParsedMatch | None:
    """Parse a single match div from the match card."""
    text = div.get_text(" ", strip=True)
    if not text or len(text) < 5:
        return None

    # Detect match type
    match_type_text = ""
    type_span = div.find("span", class_="MatchType")
    if type_span:
        match_type_text = type_span.get_text(strip=True)
    match_type = classify_match_type(match_type_text or text)

    # Detect title match
    title_match = bool(re.search(
        r"(championship|title)", text, re.IGNORECASE
    ))

    # Duration
    duration = None
    dur_match = re.search(r"(\d+:\d+)", text)
    if dur_match:
        duration = parse_duration(dur_match.group(1))

    # Rating
    rating = None
    rating_span = div.find("span", class_="star-rating")
    if rating_span:
        star_text = rating_span.get_text(strip=True)
        try:
            rating = float(star_text)
        except ValueError:
            pass

    # Stipulation
    stipulation = None
    stip_span = div.find("span", class_="MatchStipulation")
    if stip_span:
        stipulation = stip_span.get_text(strip=True)

    # Parse participants — look for wrestler links and result indicators
    participants = _parse_participants(div, text)

    return ParsedMatch(
        match_order=order,
        match_type=match_type,
        stipulation=stipulation,
        duration_seconds=duration,
        title_match=title_match,
        rating=rating,
        participants=participants,
    )


def _parse_participants(div: Tag, full_text: str) -> list[ParsedParticipant]:
    """Extract match participants and their results from a match div."""
    participants = []

    # Find wrestler links
    wrestler_links = div.find_all("a", href=re.compile(r"worker"))
    if not wrestler_links:
        return participants

    # Determine winner — typically text contains "defeat" or "over"
    # Common patterns: "A defeat B", "A & B defeat C & D", "A draw B"
    is_draw = bool(re.search(r"\b(draw|time.?limit|no.?contest|double)\b", full_text, re.IGNORECASE))
    is_no_contest = bool(re.search(r"\bno.?contest\b", full_text, re.IGNORECASE))
    is_dq = bool(re.search(r"\b(disqualif|DQ)\b", full_text, re.IGNORECASE))
    is_countout = bool(re.search(r"\bcountout\b", full_text, re.IGNORECASE))

    defeat_match = re.search(r"\bdefeat", full_text, re.IGNORECASE)
    defeat_pos = defeat_match.start() if defeat_match else len(full_text)

    for link in wrestler_links:
        name = link.get_text(strip=True)
        if not name:
            continue

        # Determine result based on position relative to "defeat"
        link_pos = full_text.find(name)

        if is_no_contest:
            result = "no_contest"
        elif is_draw:
            result = "draw"
        elif is_dq:
            result = "dq" if link_pos > defeat_pos else "win"
        elif is_countout:
            result = "countout" if link_pos > defeat_pos else "win"
        elif link_pos < defeat_pos:
            result = "win"
        else:
            result = "loss"

        participants.append(ParsedParticipant(
            name=name,
            result=result,
        ))

    return participants
