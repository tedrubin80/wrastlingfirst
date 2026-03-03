"""
Ringside Analytics — Seed Script
Loads wrestlers_roster_2026.csv into the promotions and wrestlers tables.
"""

import csv
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://ringside:ringside@localhost:5432/ringside"
)

CSV_PATH = Path(__file__).parent / "wrestlers_roster_2026.csv"

# Map CSV organization values to promotion records
PROMOTIONS = {
    "WWE": {
        "name": "World Wrestling Entertainment",
        "abbreviation": "WWE",
        "founded": "1980-06-06",
        "defunct": None,
        "parent_org": None,
    },
    "AEW": {
        "name": "All Elite Wrestling",
        "abbreviation": "AEW",
        "founded": "2019-01-01",
        "defunct": None,
        "parent_org": None,
    },
}

# Historical promotions seeded for future scraper data
HISTORICAL_PROMOTIONS = [
    {
        "name": "World Championship Wrestling",
        "abbreviation": "WCW",
        "founded": "1988-11-01",
        "defunct": "2001-03-26",
        "parent_org": None,
    },
    {
        "name": "Extreme Championship Wrestling",
        "abbreviation": "ECW",
        "founded": "1992-06-01",
        "defunct": "2001-04-04",
        "parent_org": None,
    },
    {
        "name": "Total Nonstop Action Wrestling",
        "abbreviation": "TNA",
        "founded": "2002-05-10",
        "defunct": None,
        "parent_org": None,
    },
    {
        "name": "NXT",
        "abbreviation": "NXT",
        "founded": "2010-02-23",
        "defunct": None,
        "parent_org": "WWE",
    },
]

STATUS_MAP = {
    "Active": "active",
    "Inactive": "inactive",
    "Injured": "injured",
    "Free Agent": "free_agent",
    "Retired": "retired",
    "Deceased": "deceased",
}

GENDER_MAP = {
    "Male": "male",
    "Female": "female",
}


def seed_promotions(cur) -> dict[str, int]:
    """Insert all promotions and return abbreviation -> id mapping."""
    all_promos = list(PROMOTIONS.values()) + HISTORICAL_PROMOTIONS

    for promo in all_promos:
        cur.execute(
            """
            INSERT INTO promotions (name, abbreviation, founded, defunct, parent_org)
            VALUES (%(name)s, %(abbreviation)s, %(founded)s, %(defunct)s, %(parent_org)s)
            ON CONFLICT (abbreviation) DO UPDATE SET
                name = EXCLUDED.name,
                founded = EXCLUDED.founded,
                defunct = EXCLUDED.defunct,
                parent_org = EXCLUDED.parent_org
            """,
            promo,
        )

    cur.execute("SELECT abbreviation, id FROM promotions")
    return dict(cur.fetchall())


def load_csv(path: Path) -> list[dict]:
    """Read the roster CSV and return list of row dicts."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def seed_wrestlers(cur, rows: list[dict], promo_ids: dict[str, int]) -> dict:
    """Insert wrestlers from CSV rows. Deduplicates by ring_name + promotion."""
    seen = set()
    inserted = 0
    skipped = 0
    values = []

    for row in rows:
        ring_name = row["wrestler_name"].strip()
        org = row["organization"].strip()
        brand = row["brand"].strip()
        gender = GENDER_MAP.get(row["gender"].strip(), "male")
        status = STATUS_MAP.get(row["status"].strip(), "active")

        # For NXT brand under WWE, use NXT promotion if it exists
        if org == "WWE" and brand == "NXT":
            promo_id = promo_ids.get("NXT", promo_ids.get("WWE"))
        else:
            promo_id = promo_ids.get(org)

        if promo_id is None:
            print(f"  WARN: Unknown organization '{org}' for {ring_name}, skipping")
            skipped += 1
            continue

        # Deduplicate: same name + same promotion = skip
        dedup_key = (ring_name.lower(), promo_id)
        if dedup_key in seen:
            print(f"  DEDUP: Skipping duplicate '{ring_name}' in {org}/{brand}")
            skipped += 1
            continue
        seen.add(dedup_key)

        values.append((ring_name, gender, status, promo_id, brand))

    if values:
        execute_values(
            cur,
            """
            INSERT INTO wrestlers (ring_name, gender, status, primary_promotion_id, brand)
            VALUES %s
            ON CONFLICT DO NOTHING
            """,
            values,
            template="(%s, %s::gender_type, %s::wrestler_status, %s, %s)",
        )
        inserted = cur.rowcount

    return {"inserted": inserted, "skipped": skipped, "total_rows": len(rows)}


def seed_aliases(cur):
    """Create initial aliases from wrestler ring names for entity resolution."""
    cur.execute(
        """
        INSERT INTO wrestler_aliases (wrestler_id, alias, promotion_id)
        SELECT id, ring_name, primary_promotion_id
        FROM wrestlers
        ON CONFLICT DO NOTHING
        """
    )
    return cur.rowcount


def main():
    if not CSV_PATH.exists():
        print(f"ERROR: CSV not found at {CSV_PATH}")
        sys.exit(1)

    print(f"Connecting to database...")
    conn = psycopg2.connect(DB_URL)

    try:
        with conn:
            with conn.cursor() as cur:
                # Seed promotions
                print("Seeding promotions...")
                promo_ids = seed_promotions(cur)
                print(f"  {len(promo_ids)} promotions loaded: {', '.join(promo_ids.keys())}")

                # Load and seed wrestlers
                print(f"Loading CSV from {CSV_PATH}...")
                rows = load_csv(CSV_PATH)
                print(f"  {len(rows)} rows read")

                print("Seeding wrestlers...")
                result = seed_wrestlers(cur, rows, promo_ids)
                print(f"  {result['inserted']} inserted, {result['skipped']} skipped")

                # Create initial aliases
                print("Creating initial aliases...")
                alias_count = seed_aliases(cur)
                print(f"  {alias_count} aliases created")

                # Summary
                cur.execute("SELECT count(*) FROM promotions")
                promo_count = cur.fetchone()[0]
                cur.execute("SELECT count(*) FROM wrestlers")
                wrestler_count = cur.fetchone()[0]
                cur.execute("SELECT count(*) FROM wrestler_aliases")
                alias_total = cur.fetchone()[0]

                print(f"\n=== Seed Complete ===")
                print(f"  Promotions:  {promo_count}")
                print(f"  Wrestlers:   {wrestler_count}")
                print(f"  Aliases:     {alias_total}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
