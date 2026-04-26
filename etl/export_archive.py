"""Export Ringside DB snapshot to parquet/CSV + publish to Kaggle and Hugging Face.

Purpose
-------
Make the raw match/wrestler data from the ringside Postgres DB the canonical
public source of truth, mirrored on two archives:

  * Kaggle dataset: theodorerubin/ringside-wrestling-archive
  * HF  dataset:   datamatters24/ringside-analytics

Companion to the trained model on Kaggle Models
(``theodorerubin/ringside-analytics-match-winner``).

Subcommands
-----------
  export       Dump 9 source tables to parquet + CSV under data/kaggle/
                Also builds match_view (denormalized) and feature_matrix.
                Bundles dataset/ docs (README, dictionary, examples) on top.
  kaggle       Push data/kaggle/ to Kaggle (create on first run, version after)
  huggingface  Push data/kaggle/ to Hugging Face Hub
  all          Run export + both uploads in sequence

Excluded columns
----------------
* tsvector columns (``search_vector``) — Postgres-internal, not serializable
* ``predictions`` table — empty, ML-generated, not source data
* ``wrestler_stats_rolling`` — derived feature store, rebuilds nightly
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
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

REPO_ROOT = Path("/var/www/wrastling")
OUT_DIR = REPO_ROOT / "data" / "kaggle"
DATASET_DOCS = REPO_ROOT / "dataset"   # canonical sources; copied into OUT_DIR on export

# Kaggle dataset metadata — generated each export so data/ can stay gitignored
# and Kaggle archive's subtitle/description/keywords don't drift between runs.
KAGGLE_DATASET_METADATA = {
    "title": "Ringside Analytics Wrestling Dataset",
    "id": "theodorerubin/ringside-wrestling-archive",
    "subtitle": "482K pro wrestling matches, 1980–present — relational + ML-ready",
    "description": (
        "A relational snapshot of professional wrestling history from 1980 to the present: "
        "482K matches, 731K wrestler-match participations, 35K events, 12.8K wrestlers across "
        "WWE, AEW, WCW, ECW, NXT, TNA, and others. Ships in three forms: nine joinable "
        "parquet/CSV tables (matches, match_participants, wrestlers, wrestler_aliases, events, "
        "promotions, titles, title_reigns, alignment_turns); a denormalized match_view for "
        "users who want one-row-per-(match,wrestler) without joins; and a 35-feature "
        "feature_matrix that reproduces the trained model exactly. Sourced from public "
        "Cagematch.net scrapes and the alexdiresta profightdb dump, normalized into a Postgres "
        "schema and exported with snappy compression. Includes a full data dictionary, runnable "
        "examples in Python/DuckDB/SQL, and citation file. Companion trained model at "
        "theodorerubin/ringside-analytics-match-winner."
    ),
    "licenses": [{"name": "CC0-1.0"}],
    "keywords": ["sports", "classification", "tabular", "data analytics", "beginner"],
    "collaborators": [],
    "data": [],
    "resources": [
        # Source tables (parquet + csv)
        {"path": "promotions.parquet",         "description": "Promotion lookup (WWE, AEW, WCW, ECW, NXT, TNA)"},
        {"path": "wrestlers.parquet",          "description": "Wrestler identity table"},
        {"path": "wrestler_aliases.parquet",   "description": "Alternate ring names per wrestler"},
        {"path": "events.parquet",             "description": "Wrestling events with date, venue, promotion"},
        {"path": "matches.parquet",            "description": "Match cards with type, stipulation, rating"},
        {"path": "match_participants.parquet", "description": "Wrestler-per-match rows with result label"},
        {"path": "titles.parquet",             "description": "Championship belts per promotion"},
        {"path": "title_reigns.parquet",       "description": "Reign start/end and defenses"},
        {"path": "alignment_turns.parquet",    "description": "Face/heel/tweener transitions"},
        # CSV mirrors
        {"path": "promotions.csv",         "description": "CSV mirror of promotions"},
        {"path": "wrestlers.csv",          "description": "CSV mirror of wrestlers"},
        {"path": "wrestler_aliases.csv",   "description": "CSV mirror of wrestler_aliases"},
        {"path": "events.csv",             "description": "CSV mirror of events"},
        {"path": "matches.csv",            "description": "CSV mirror of matches"},
        {"path": "match_participants.csv", "description": "CSV mirror of match_participants"},
        {"path": "titles.csv",             "description": "CSV mirror of titles"},
        {"path": "title_reigns.csv",       "description": "CSV mirror of title_reigns"},
        {"path": "alignment_turns.csv",    "description": "CSV mirror of alignment_turns"},
        # Derived ML-ready tables
        {"path": "match_view.parquet",     "description": "Denormalized one-row-per-(match,wrestler) — no joins required"},
        {"path": "match_view.csv",         "description": "CSV mirror of match_view"},
        {"path": "feature_matrix.parquet", "description": "35-feature ML-ready matrix used by the trained model"},
        {"path": "feature_matrix.csv",     "description": "CSV mirror of feature_matrix"},
        # Documentation
        {"path": "README.md",              "description": "Dataset card with schema, joins, queries, caveats"},
        {"path": "DATA_DICTIONARY.md",     "description": "Column-by-column documentation for every table"},
        {"path": "CITATION.cff",           "description": "Academic-style citation (Citation File Format)"},
        {"path": "CHANGELOG.md",           "description": "Version history"},
        {"path": "manifest.json",          "description": "Export manifest — row counts, columns, UTC timestamp"},
        # Examples
        {"path": "examples/python_quickstart.py", "description": "Python loading + basic queries"},
        {"path": "examples/duckdb_queries.sql",   "description": "DuckDB SQL recipes against the parquets"},
        {"path": "examples/pandas_recipes.ipynb", "description": "Pandas cookbook — 10 common analyses"},
    ],
}

# Table -> explicit column list. Avoids tsvector + generated columns.
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


def export_source_tables(out_dir: Path) -> dict:
    """Query each source table and write to parquet + CSV. Returns manifest."""
    manifest: dict = {
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

                pq_path = out_dir / f"{table}.parquet"
                df.to_parquet(pq_path, compression="snappy", index=False)

                csv_path = out_dir / f"{table}.csv"
                df.to_csv(csv_path, index=False)

                manifest["tables"][table] = {
                    "rows": len(df),
                    "columns": list(df.columns),
                    "parquet_size_mb": round(pq_path.stat().st_size / 1024 / 1024, 2),
                    "csv_size_mb":     round(csv_path.stat().st_size / 1024 / 1024, 2),
                }
                logger.info(
                    "export_done",
                    table=table,
                    rows=len(df),
                    parquet_mb=manifest["tables"][table]["parquet_size_mb"],
                    csv_mb=manifest["tables"][table]["csv_size_mb"],
                )
            except Exception:
                logger.exception("export_failed", table=table)
                raise
    finally:
        conn.close()

    return manifest


def export_match_view(out_dir: Path, manifest: dict) -> None:
    """Build denormalized one-row-per-(match,wrestler) table.

    Joins matches + events + promotions + match_participants + wrestlers and
    pre-computes per-match counts. Saves users from doing the joins themselves.
    """
    logger.info("match_view_start")
    conn = psycopg2.connect(DB_URL)
    try:
        query = """
        SELECT
            mp.match_id,
            mp.wrestler_id,
            w.ring_name,
            m.event_id,
            e.date           AS event_date,
            EXTRACT(YEAR FROM e.date)::int AS year,
            e.event_type,
            p.id             AS promotion_id,
            p.abbreviation   AS promotion_abbr,
            m.match_type,
            m.stipulation,
            m.title_match,
            m.duration_seconds,
            m.rating,
            mp.team_number,
            mp.entry_order,
            mp.elimination_order,
            mp.result,
            (SELECT COUNT(*) FROM match_participants mp2 WHERE mp2.match_id = mp.match_id)         AS n_participants,
            (SELECT COUNT(DISTINCT mp2.team_number) FROM match_participants mp2 WHERE mp2.match_id = mp.match_id) AS n_teams
        FROM match_participants mp
        JOIN matches    m ON m.id = mp.match_id
        JOIN events     e ON e.id = m.event_id
        JOIN promotions p ON p.id = e.promotion_id
        JOIN wrestlers  w ON w.id = mp.wrestler_id
        ORDER BY e.date, mp.match_id, mp.team_number, mp.entry_order
        """
        df = pd.read_sql_query(query, conn)
        df["is_singles"] = (df["n_participants"] == 2) & (df["n_teams"] == 2)

        pq_path = out_dir / "match_view.parquet"
        df.to_parquet(pq_path, compression="snappy", index=False)
        csv_path = out_dir / "match_view.csv"
        df.to_csv(csv_path, index=False)

        manifest["match_view"] = {
            "rows": len(df),
            "columns": list(df.columns),
            "parquet_size_mb": round(pq_path.stat().st_size / 1024 / 1024, 2),
            "csv_size_mb":     round(csv_path.stat().st_size / 1024 / 1024, 2),
        }
        logger.info("match_view_done", rows=len(df))
    finally:
        conn.close()


def export_feature_matrix(out_dir: Path, manifest: dict) -> None:
    """Dump the 35-feature ML-ready matrix used by the trained model.

    Imports ml.features lazily so users without the ML deps installed can still
    run the parquet export.
    """
    try:
        sys.path.insert(0, str(REPO_ROOT / "ml"))
        from features import build_feature_matrix  # type: ignore
    except ImportError:
        logger.warning("feature_matrix_skipped", reason="ml.features unavailable")
        return

    logger.info("feature_matrix_start")
    df = build_feature_matrix()

    pq_path = out_dir / "feature_matrix.parquet"
    df.to_parquet(pq_path, compression="snappy", index=False)
    csv_path = out_dir / "feature_matrix.csv"
    df.to_csv(csv_path, index=False)

    manifest["feature_matrix"] = {
        "rows": len(df),
        "columns": list(df.columns),
        "parquet_size_mb": round(pq_path.stat().st_size / 1024 / 1024, 2),
        "csv_size_mb":     round(csv_path.stat().st_size / 1024 / 1024, 2),
    }
    logger.info("feature_matrix_done", rows=len(df), cols=len(df.columns))


def bundle_docs(out_dir: Path) -> None:
    """Copy README, dictionary, examples, citation, changelog from dataset/ → out_dir."""
    if not DATASET_DOCS.exists():
        logger.warning("dataset_docs_missing", path=str(DATASET_DOCS))
        return

    # Top-level files
    for name in ("README.md", "DATA_DICTIONARY.md", "CITATION.cff", "CHANGELOG.md"):
        src = DATASET_DOCS / name
        if src.exists():
            shutil.copy2(src, out_dir / name)
            logger.info("doc_bundled", file=name)

    # Examples directory
    examples_src = DATASET_DOCS / "examples"
    if examples_src.exists():
        examples_dst = out_dir / "examples"
        if examples_dst.exists():
            shutil.rmtree(examples_dst)
        shutil.copytree(examples_src, examples_dst)
        logger.info("examples_bundled", count=len(list(examples_dst.iterdir())))


def run_export(out_dir: Path) -> dict:
    """Full export: source tables, match_view, feature_matrix, docs, manifest."""
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = export_source_tables(out_dir)
    export_match_view(out_dir, manifest)
    export_feature_matrix(out_dir, manifest)
    bundle_docs(out_dir)

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))
    logger.info("manifest_written", path=str(manifest_path))

    meta_path = out_dir / "dataset-metadata.json"
    meta_path.write_text(
        json.dumps(KAGGLE_DATASET_METADATA, indent=2, ensure_ascii=False)
    )
    logger.info("dataset_metadata_written", path=str(meta_path))

    return manifest


def run_kaggle(out_dir: Path) -> int:
    """Push parquets to Kaggle. Creates on first run, versions after."""
    metadata = out_dir / "dataset-metadata.json"
    if not metadata.exists():
        logger.error("missing_kaggle_metadata", path=str(metadata))
        return 1

    slug = KAGGLE_DATASET_METADATA["id"]
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
        ignore_patterns=["dataset-metadata.json"],
    )
    logger.info("hf_push_complete", repo_id=repo_id)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "command",
        choices=["export", "kaggle", "huggingface", "all"],
        help="export to parquet/CSV, or push to a target, or all",
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
