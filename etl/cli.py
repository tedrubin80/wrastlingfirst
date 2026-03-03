"""CLI entry point for the ETL pipeline."""

import argparse
import os
import sys
from pathlib import Path

import psycopg2
import structlog

from etl.load import DataLoader
from etl.stats import recompute_rolling_stats, compute_streaks

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)

logger = structlog.get_logger(__name__)

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://ringside:ringside@localhost:5432/ringside",
)


def main():
    parser = argparse.ArgumentParser(
        description="Load scraped match data into PostgreSQL"
    )
    parser.add_argument(
        "--input-dir",
        default="./output",
        help="Directory containing scraped JSON files (default: ./output)",
    )
    parser.add_argument(
        "--file",
        help="Load a single JSON file instead of a directory",
    )
    parser.add_argument(
        "--skip-stats",
        action="store_true",
        help="Skip rolling stats recomputation",
    )
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Only recompute rolling stats (no data load)",
    )

    args = parser.parse_args()

    logger.info("etl_starting")

    conn = psycopg2.connect(DB_URL)

    try:
        if not args.stats_only:
            loader = DataLoader(conn)

            if args.file:
                path = Path(args.file)
                if not path.exists():
                    logger.error("file_not_found", path=str(path))
                    sys.exit(1)
                loader.load_file(path)
            else:
                input_dir = Path(args.input_dir)
                if not input_dir.exists():
                    logger.error("input_dir_not_found", path=str(input_dir))
                    sys.exit(1)

                json_files = sorted(input_dir.glob("*.json"))
                if not json_files:
                    logger.warning("no_json_files", path=str(input_dir))
                    sys.exit(0)

                for path in json_files:
                    if path.name == "all_events.json":
                        continue  # Skip combined file, load per-promotion files
                    loader.load_file(path)

            # Report unresolved names
            unresolved = loader.get_unresolved_names()
            if unresolved:
                logger.warning(
                    "unresolved_wrestlers",
                    count=len(unresolved),
                    names=unresolved[:20],
                )
                # Write full list to file for manual review
                unresolved_path = Path("./unresolved_wrestlers.txt")
                unresolved_path.write_text(
                    "\n".join(unresolved), encoding="utf-8"
                )
                logger.info(
                    "unresolved_written",
                    path=str(unresolved_path),
                    count=len(unresolved),
                )

            print(f"\nLoad complete: {loader.stats}")

        # Recompute stats
        if not args.skip_stats:
            logger.info("recomputing_stats")
            stats_count = recompute_rolling_stats(conn)
            streak_count = compute_streaks(conn)
            print(f"Stats recomputed for {stats_count} wrestlers, "
                  f"streaks updated for {streak_count}.")

    finally:
        conn.close()

    logger.info("etl_complete")


if __name__ == "__main__":
    main()
