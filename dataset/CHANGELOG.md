# Changelog

All notable changes to the Ringside Wrestling Archive dataset.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
loosely (major = schema change, minor = added artifacts, patch = data refresh).

## [1.1.0] — 2026-04-26

### Added
- **CSV mirrors** of all 9 source tables for users without `pyarrow`.
- **`match_view.parquet`** — denormalized one-row-per-(match, wrestler) join
  combining matches + events + promotions + participants. ML-ready, no joins required.
- **`feature_matrix.parquet`** — the 35-feature ML-ready matrix used by the
  trained model. Lets users reproduce the published model exactly without
  rebuilding the feature pipeline.
- **`DATA_DICTIONARY.md`** — column-by-column documentation for all tables,
  including the new derived ones and CSV-vs-parquet differences.
- **`CITATION.cff`** — academic-style citation file (GitHub renders).
- **`examples/`** — runnable starter scripts:
  - `python_quickstart.py` (pandas loading + basic queries)
  - `duckdb_queries.sql` (analytical SQL recipes)
  - `pandas_recipes.ipynb` (10-recipe cookbook)

### Changed
- `dataset-metadata.json` rebuilt to reference all new artifacts.
- README expanded with file-format guidance.

## [1.0.0] — 2026-04-19

### Added
- Initial public release.
- 9 source tables as parquet (snappy compression):
  promotions, wrestlers, wrestler_aliases, events, matches,
  match_participants, titles, title_reigns, alignment_turns.
- Dataset card (README.md) with schema diagram, starter queries, caveats.
- Manifest with row counts and UTC export timestamp.
- License: CC0-1.0.
- Mirror published on Hugging Face: `datamatters24/ringside-analytics`.
