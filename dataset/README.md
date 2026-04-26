---
license: cc0-1.0
task_categories:
  - tabular-classification
language:
  - en
tags:
  - sports
  - wrestling
  - wwe
  - aew
  - wcw
  - ecw
  - match-data
  - relational
pretty_name: Ringside Analytics — Pro Wrestling Match Archive
size_categories:
  - 100K<n<1M
configs:
  - config_name: matches
    data_files: matches.parquet
  - config_name: match_participants
    data_files: match_participants.parquet
  - config_name: wrestlers
    data_files: wrestlers.parquet
  - config_name: events
    data_files: events.parquet
  - config_name: promotions
    data_files: promotions.parquet
  - config_name: wrestler_aliases
    data_files: wrestler_aliases.parquet
  - config_name: titles
    data_files: titles.parquet
  - config_name: title_reigns
    data_files: title_reigns.parquet
  - config_name: alignment_turns
    data_files: alignment_turns.parquet
---

# Ringside Analytics — Pro Wrestling Match Archive

A relational snapshot of professional wrestling history from 1980 to the present:
**292K matches, 611K wrestler-match participations, 35K events, and 12.8K
wrestlers** across WWE, AEW, WCW, ECW, NXT, TNA, and others. Sourced from
public Cagematch.net scrapes and the alexdiresta profightdb dump, normalized
into a Postgres schema, and exported as parquet files that preserve the
relational structure (one file per table, joinable by `id`).

This is the source-of-truth companion to the trained model at
[theodorerubin/ringside-wrestling-archive-match-winner](https://www.kaggle.com/models/theodorerubin/ringside-wrestling-archive-match-winner).
If you want to train your own model, reshape the features, or just explore
40+ years of booking patterns — start here.

## Files

| File | Rows | Description |
|---|---:|---|
| `matches.parquet` | 292,780 | One row per match. Type, stipulation, duration, title match flag, Cagematch rating. |
| `match_participants.parquet` | 611,515 | One row per wrestler-per-match. `result` is the label for outcome prediction. |
| `wrestlers.parquet` | 12,814 | Ring name, real name, gender, debut date, status. |
| `wrestler_aliases.parquet` | 13,230 | Alternate ring names with active-period bounds. |
| `events.parquet` | 35,064 | Event name, date, venue, city, country, event type. |
| `promotions.parquet` | 6 | WWE, AEW, WCW, ECW, NXT, TNA with founding / defunct dates. |
| `titles.parquet` | 121 | Championship belts per promotion. |
| `title_reigns.parquet` | 1,753 | Reign start/end + number of defenses. |
| `alignment_turns.parquet` | 631 | Face / heel / tweener transitions per wrestler. |
| `manifest.json` | — | Export manifest: row counts, columns, UTC timestamp. |

## Schema (join keys)

```
promotions.id ─┬─< wrestlers.primary_promotion_id
               ├─< events.promotion_id
               ├─< titles.promotion_id
               └─< wrestler_aliases.promotion_id

wrestlers.id ──┬─< match_participants.wrestler_id
               ├─< wrestler_aliases.wrestler_id
               ├─< title_reigns.wrestler_id
               └─< alignment_turns.wrestler_id

events.id ─────┬─< matches.event_id
               └─< alignment_turns.event_id  (nullable)

matches.id ────── match_participants.match_id

titles.id ─────── title_reigns.title_id
```

## Starter queries

```python
import pandas as pd

matches = pd.read_parquet("matches.parquet")
participants = pd.read_parquet("match_participants.parquet")
wrestlers = pd.read_parquet("wrestlers.parquet")

# Every match The Rock has wrestled, with opponents
rock_id = wrestlers.query("ring_name == 'The Rock'")["id"].iloc[0]
rock_matches = participants[participants["wrestler_id"] == rock_id]
```

```sql
-- If you load these into DuckDB:
SELECT w.ring_name, COUNT(*) AS wins
FROM match_participants mp
JOIN wrestlers w ON w.id = mp.wrestler_id
WHERE mp.result = 'win'
GROUP BY 1
ORDER BY 2 DESC
LIMIT 20;
```

## Provenance

- **Cagematch.net** (public HTML scrape, non-commercial use): the bulk of
  match-level data for 1990-present.
- **alexdiresta/all-wwe-and-wwf-matches** Kaggle dataset (profightdb dump):
  cross-validation + pre-1990 coverage.
- **Normalization + dedup**: entity resolution on wrestler names,
  match-type classification into a fixed ENUM, and natural-key deduplication
  to collapse records across sources.

The ETL code and scraper are open source at
[tedrubin80/wrastlingfirst](https://github.com/tedrubin80/wrastlingfirst).

## Caveats

- **Kayfabe, not athletics.** Pro wrestling is scripted. A `result` field
  records *who was booked to win*, not who would win an athletic contest.
- **Temporal coverage is uneven.** 2000-present is well-covered; 1980s are
  thinner, especially for regional/territory promotions.
- **Gender imbalance.** Women's division sample size is smaller — expect
  wider confidence intervals for any women's-division model.
- **Ratings are crowd-sourced** (Cagematch user ratings). They're a proxy
  for match quality as perceived by Internet wrestling fans — biased toward
  work-rate and away from entertainment/story.

## License

Released under **CC0 1.0** (public domain dedication). Attribution is
appreciated but not required. Note that the underlying sources
(Cagematch.net, profightdb) have their own terms; this archive is a
derivative work made available for research and entertainment.

## Citation

```bibtex
@dataset{ringside_analytics_2026,
  author = {Rubin, Theodore},
  title  = {Ringside Analytics: Pro Wrestling Match Archive (1980--present)},
  year   = {2026},
  url    = {https://www.kaggle.com/datasets/theodorerubin/ringside-wrestling-archive}
}
```
