"""Export Ringside DB snapshot to parquet + publish to Kaggle and Hugging Face.

Purpose
-------
Make the raw match/wrestler data from the ringside Postgres DB the canonical
public source of truth, mirrored on two archives:

  * Kaggle dataset: theodorerubin/ringside-analytics
  * HF  dataset:   datamatters24/ringside-analytics

This is the companion to the trained-model artifact on Kaggle Models
(``theodorerubin/ringside-analytics-match-winner``), which cites this dataset
via its ``provenanceSources`` field.

Subcommands
-----------
  export       Dump nine source tables to parquet under data/kaggle/
  kaggle       Push data/kaggle/ to Kaggle (create on first run, version after)
  huggingface  Push data/kaggle/ to Hugging Face Hub
  all          Run export + both uploads in sequence

Excluded columns
----------------
* tsvector columns (``search_vector``) — Postgres-internal, not serializable
* ``predictions`` table — empty and ML-generated, not source data
* ``wrestler_stats_rolling`` — derived feature store, rebuilds nightly
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import psycopg2
import structlog

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

OUT_DIR = Path("/var/www/wrastling/data/kaggle")

# Kaggle dataset metadata — regenerated each export so data/ can stay gitignored
# and the Kaggle archive's subtitle/description/keywords don't drift between runs.
KAGGLE_DATASET_METADATA = {
    "title": "Ringside Analytics Wrestling Dataset",
    "id": "theodorerubin/ringside-wrestling-archive",
    "subtitle": "292K pro wrestling matches, 1980–present — 9 relational parquet files",
    "description": (
        "A relational snapshot of professional wrestling history from 1980 to the present: "
        "292,780 matches, 611,515 wrestler-match participations, 35,064 events, and 12,814 "
        "wrestlers across WWE, AEW, WCW, ECW, NXT, TNA, and others. Nine joinable parquet "
        "files preserve the full schema — matches, match_participants, wrestlers, "
        "wrestler_aliases, events, promotions, titles, title_reigns, and alignment_turns. "
        "Sourced from public Cagematch.net scrapes and the alexdiresta profightdb dump, "
        "normalized into a Postgres schema and exported with snappy compression. Full "
        "dataset card, join diagram, starter queries, and caveats in the attached README.md. "
        "Companion trained model at theodorerubin/ringside-analytics-match-winner."
    ),
    "licenses": [{"name": "CC0-1.0"}],
    "keywords": ["sports", "classification", "tabular", "data analytics", "beginner"],
    "collaborators": [],
    "data": [],
    "resources": [
        {"path": "promotions.parquet",         "description": "Promotion lookup (WWE, AEW, WCW, ECW, NXT, TNA)"},
        {"path": "wrestlers.parquet",          "description": "Wrestler identity table — ring name, real name, debut date, status"},
        {"path": "wrestler_aliases.parquet",   "description": "Alternate ring names per wrestler, with active-period bounds"},
        {"path": "events.parquet",             "description": "Wrestling events — date, venue, city, promotion, event type"},
        {"path": "matches.parquet",            "description": "Match cards — type, stipulation, duration, title match flag, rating"},
        {"path": "match_participants.parquet", "description": "Wrestler-per-match rows with result (win/loss/draw/dq/no_contest/countout)"},
        {"path": "titles.parquet",             "description": "Championship belts per promotion"},
        {"path": "title_reigns.parquet",       "description": "Reign start/end dates plus number of defenses"},
        {"path": "alignment_turns.parquet",    "description": "Face / heel / tweener transitions per wrestler"},
        {"path": "manifest.json",              "description": "Export manifest — row counts, columns, UTC generation timestamp"},
    ],
}

# Table -> explicit column list. Avoids tsvector + generated columns, and
# makes the public schema reviewable at a glance.
TABLES: dict[str, list[str]] = {
    "promotions": [
        "id", "name", "abbreviation", "founded", "defunct", "parent_org",
        "created_at", "updated_at",
    ],
    "wrestlers": [
        "id", "ring_name", "real_name", "gender", "birth_date", "debut_date",
        "status", "primary_promotion_id", "brand", "billed_from", "image_url",
        "created_at", "updated_at",
    ],
    "wrestler_aliases": [
        "id", "wrestler_id", "alias", "promotion_id",
        "active_from", "active_to", "created_at",
    ],
    "events": [
        "id", "name", "promotion_id", "date", "venue", "city", "state",
        "country", "event_type", "cagematch_id", "created_at", "updated_at",
    ],
    "matches": [
        "id", "event_id", "match_order", "match_type", "stipulation",
        "duration_seconds", "title_match", "rating", "cagematch_id",
        "created_at", "updated_at",
    ],
    "match_participants": [
        "id", "match_id", "wrestler_id", "team_number", "result",
        "entry_order", "elimination_order", "created_at",
    ],
    "titles": [
        "id", "name", "promotion_id", "established", "retired", "active",
        "created_at", "updated_at",
    ],
    "title_reigns": [
        "id", "title_id", "wrestler_id", "won_date", "lost_date", "defenses",
        "won_at_event_id", "lost_at_event_id", "created_at", "updated_at",
    ],
    "alignment_turns": [
        "id", "wrestler_id", "from_alignment", "to_alignment", "turn_date",
        "event_id", "description", "source", "created_at",
    ],
}


def run_export(out_dir: Path) -> dict:
    """Query each table and write to parquet. Returns a manifest dict."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "postgresql://ringside (local)",
        "tables": {},
    }

    conn = psycopg2.connect(DB_URL)
    try:
        for table, cols in TABLES.items():
            try:
                col_sql = ", ".join(cols)
                query = f"SELECT {col_sql} FROM {table} ORDER BY id"
                logger.info("export_start", table=table)
                df = pd.read_sql_query(query, conn)
                path = out_dir / f"{table}.parquet"
                df.to_parquet(path, compression="snappy", index=False)
                size_mb = path.stat().st_size / 1024 / 1024
                manifest["tables"][table] = {
                    "rows": len(df),
                    "columns": list(df.columns),
                    "file": path.name,
                    "size_mb": round(size_mb, 2),
                }
                logger.info(
                    "export_done",
                    table=table,
                    rows=len(df),
                    size_mb=round(size_mb, 2),
                )
            except Exception:
                logger.exception("export_failed", table=table)
                raise
    finally:
        conn.close()

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    logger.info("manifest_written", path=str(manifest_path))

    # Regenerate Kaggle dataset metadata each run so data/ can stay gitignored
    # without losing subtitle/description/keyword customizations.
    meta_path = out_dir / "dataset-metadata.json"
    meta_path.write_text(
        json.dumps(KAGGLE_DATASET_METADATA, indent=2, ensure_ascii=False)
    )
    logger.info("dataset_metadata_written", path=str(meta_path))

    return manifest


def run_kaggle(out_dir: Path) -> int:
    """Push parquets to Kaggle. Creates the dataset on first run, versions after."""
    import subprocess

    metadata = out_dir / "dataset-metadata.json"
    if not metadata.exists():
        logger.error("missing_kaggle_metadata", path=str(metadata))
        return 1

    slug = KAGGLE_DATASET_METADATA["id"]  # owner/slug
    cmd_exists = ["kaggle", "datasets", "status", slug]
    result = subprocess.run(cmd_exists, capture_output=True, text=True)
    exists = "ready" in result.stdout.lower() or "private" in result.stdout.lower()

    if exists:
        cmd = [
            "kaggle", "datasets", "version", "-p", str(out_dir),
            "-m", f"Refresh {datetime.now().date().isoformat()}",
            "--dir-mode", "zip",
        ]
    else:
        cmd = [
            "kaggle", "datasets", "create", "-p", str(out_dir),
            "--dir-mode", "zip", "--public",
        ]

    logger.info("kaggle_push", cmd=" ".join(cmd))
    rc = subprocess.call(cmd)
    logger.info("kaggle_push_complete", returncode=rc)

    # `datasets version` only uploads files — subtitle/description/keywords
    # only propagate via the separate metadata --update call.
    if rc == 0 and exists:
        meta_cmd = [
            "kaggle", "datasets", "metadata", "--update", slug,
            "-p", str(out_dir),
        ]
        logger.info("kaggle_metadata_update", cmd=" ".join(meta_cmd))
        subprocess.call(meta_cmd)

    return rc


def run_huggingface(out_dir: Path) -> int:
    """Push parquets to Hugging Face Hub as a dataset repo."""
    from huggingface_hub import HfApi, create_repo

    token = os.environ.get("HF_TOKEN")
    if not token:
        logger.error("HF_TOKEN_missing")
        return 1

    repo_id = "datamatters24/ringside-analytics"
    api = HfApi(token=token)

    try:
        create_repo(
            repo_id, repo_type="dataset", token=token, exist_ok=True, private=False,
        )
    except Exception:
        logger.exception("hf_create_repo_failed")
        return 1

    api.upload_folder(
        folder_path=str(out_dir),
        repo_id=repo_id,
        repo_type="dataset",
        token=token,
        commit_message=f"Refresh {datetime.now().date().isoformat()}",
        ignore_patterns=["dataset-metadata.json"],  # Kaggle-specific, skip on HF
    )
    logger.info("hf_push_complete", repo_id=repo_id)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "command",
        choices=["export", "kaggle", "huggingface", "all"],
        help="export to parquet, or push to a target, or all",
    )
    p.add_argument("--out", type=Path, default=OUT_DIR)
    args = p.parse_args()

    if args.command in ("export", "all"):
        run_export(args.out)

    if args.command in ("kaggle", "all"):
        rc = run_kaggle(args.out)
        if rc != 0 and args.command == "all":
            return rc

    if args.command in ("huggingface", "all"):
        rc = run_huggingface(args.out)
        if rc != 0:
            return rc

    return 0


if __name__ == "__main__":
    sys.exit(main())
