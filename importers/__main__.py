"""
Master Kaggle import pipeline.

Usage:
    python -m importers                          # Run all 4 imports in order
    python -m importers --only profightdb        # Run one specific import
    python -m importers --only wwe,ratings       # Run specific imports

Import order (optimized for deduplication):
  1. ProFightDB (363K matches — largest, becomes the base layer)
  2. WWE SQLite (88K matches — fills historical gaps)
  3. Champion (1K — enriches title flags)
  4. Ratings (8K — enriches match ratings)
"""

import argparse
import os
import sys
import time

import structlog

structlog.configure(
    processors=[
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    wrapper_class=structlog.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

log = structlog.get_logger()

IMPORTERS = {
    "profightdb": ("importers.kaggle_profightdb", "ProFightDB (363K matches)"),
    "wwe": ("importers.kaggle_wwe", "WWE SQLite (88K matches)"),
    "champion": ("importers.kaggle_champion", "WWE Champion (1K matches)"),
    "ratings": ("importers.kaggle_ratings", "WWE Ratings (8K matches)"),
    "aew": ("importers.kaggle_aew", "AEW Events & Ratings (4K matches)"),
}

IMPORT_ORDER = ["profightdb", "wwe", "champion", "ratings", "aew"]


def main():
    parser = argparse.ArgumentParser(description="Ringside Kaggle Import Pipeline")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", "postgresql://ringside:ringside@localhost:5432/ringside"),
    )
    parser.add_argument(
        "--only",
        help="Comma-separated list of importers to run (profightdb,wwe,champion,ratings)",
    )
    args = parser.parse_args()

    if args.only:
        to_run = [s.strip() for s in args.only.split(",")]
        for name in to_run:
            if name not in IMPORTERS:
                print(f"Unknown importer: {name}. Options: {', '.join(IMPORTERS.keys())}")
                sys.exit(1)
    else:
        to_run = IMPORT_ORDER

    results = {}

    for name in to_run:
        module_path, description = IMPORTERS[name]
        log.info(f"{'='*60}")
        log.info(f"Starting: {description}")
        log.info(f"{'='*60}")

        start = time.time()
        try:
            # Dynamic import
            module = __import__(module_path, fromlist=["run"])
            stats = module.run(args.database_url)
            elapsed = time.time() - start
            results[name] = {"status": "success", "stats": stats, "elapsed": f"{elapsed:.1f}s"}
            log.info(f"Completed: {description}", elapsed=f"{elapsed:.1f}s")
        except Exception as e:
            elapsed = time.time() - start
            results[name] = {"status": "error", "error": str(e), "elapsed": f"{elapsed:.1f}s"}
            log.error(f"Failed: {description}", error=str(e), elapsed=f"{elapsed:.1f}s")

    # Summary
    print("\n" + "=" * 60)
    print("IMPORT SUMMARY")
    print("=" * 60)
    for name in to_run:
        r = results.get(name, {})
        status = r.get("status", "not run")
        elapsed = r.get("elapsed", "?")
        desc = IMPORTERS[name][1]
        if status == "success":
            stats = r.get("stats", {})
            matches = stats.get("matches_imported", 0)
            wrestlers = stats.get("wrestlers_created", 0)
            print(f"  ✓ {desc}: {matches} matches, {wrestlers} new wrestlers ({elapsed})")
        else:
            print(f"  ✗ {desc}: {r.get('error', 'unknown error')} ({elapsed})")
    print("=" * 60)


if __name__ == "__main__":
    main()
