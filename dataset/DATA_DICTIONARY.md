# Data Dictionary — Ringside Wrestling Archive

Column-by-column documentation for every table in the dataset. Types reflect
the underlying Postgres schema; parquet preserves them faithfully (CSV
exports drop type info — see notes below each table).

**Conventions:**
- All `id` columns are unsigned integers, monotonically increasing.
- All timestamp columns are UTC.
- "Nullable" = `Y` means the column can be NULL/empty for some rows.
- `created_at` / `updated_at` columns track ETL provenance, not real-world events.

---

## 1. `promotions` (6 rows)

The major North American promotions covered.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | int | N | Primary key |
| `name` | text | N | Full promotion name (e.g., "World Wrestling Entertainment") |
| `abbreviation` | text | N | Common short form (`WWE`, `AEW`, `WCW`, `ECW`, `NXT`, `TNA`) |
| `founded` | date | Y | Founding date |
| `defunct` | date | Y | Closure date (null if active) |
| `parent_org` | text | Y | Parent corporation if applicable (`WWE → TKO`, `NXT → WWE`) |
| `created_at` | timestamp | N | When this row was first inserted |
| `updated_at` | timestamp | N | Last modified by ETL |

**Notes:** WCW (1988-2001) and ECW (1992-2001) are historical cohorts — their match counts won't grow.

---

## 2. `wrestlers` (12,814 rows)

Identity table. One row per unique wrestler, regardless of name changes.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | int | N | Primary key |
| `ring_name` | text | N | Canonical ring name (most-used name; alternates in `wrestler_aliases`) |
| `real_name` | text | Y | Birth/legal name where known |
| `gender` | text | Y | `M`, `F`, or `Other`. Null when undetermined from sources |
| `birth_date` | date | Y | Date of birth |
| `debut_date` | date | Y | First documented match in any promotion |
| `status` | text | Y | `active`, `retired`, `deceased`, `unknown` |
| `primary_promotion_id` | int | Y | FK → promotions.id (most-associated promotion) |
| `brand` | text | Y | Sub-roster (e.g., `Raw`, `SmackDown`, `NXT`) for current wrestlers |
| `billed_from` | text | Y | Storyline hometown ("billed from Cleveland, Ohio") |
| `image_url` | text | Y | Cagematch CDN URL (may rot — re-host before depending) |
| `created_at` | timestamp | N | Row insertion |
| `updated_at` | timestamp | N | Last update |

**Notes:** Use `wrestler_aliases` to find rows for wrestlers who have used multiple ring names (Dwayne Johnson → Rocky Maivia / The Rock).

---

## 3. `wrestler_aliases` (13,230 rows)

Alternate ring names and their active periods.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | int | N | Primary key |
| `wrestler_id` | int | N | FK → wrestlers.id |
| `alias` | text | N | The alternate name |
| `promotion_id` | int | Y | Promotion where this alias was used (null if cross-promotion) |
| `active_from` | date | Y | First documented use of the alias |
| `active_to` | date | Y | Last documented use (null if still in use) |
| `created_at` | timestamp | N | Row insertion |

**Notes:** Useful for entity resolution when joining with external sources that use different name forms.

---

## 4. `events` (35,064 rows)

One row per show — TV taping, PPV, house show, indie event.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | int | N | Primary key |
| `name` | text | N | Event name (e.g., "WrestleMania 40 Night 1") |
| `promotion_id` | int | N | FK → promotions.id |
| `date` | date | N | Event date |
| `venue` | text | Y | Arena/venue name |
| `city` | text | Y | City of event |
| `state` | text | Y | State/province (US/Canada only, mostly) |
| `country` | text | Y | Country code or name |
| `event_type` | text | Y | `ppv`, `weekly_tv`, `house_show`, `nxt_show`, `indie`, etc. |
| `cagematch_id` | int | Y | Cagematch.net's event ID — useful for re-fetching source HTML |
| `created_at` | timestamp | N | Row insertion |
| `updated_at` | timestamp | N | Last update |

**Notes:** `event_type` is most reliable for WWE/AEW; territory-era events may default to `weekly_tv` or be null.

---

## 5. `matches` (482,166 rows)

Match-level metadata. Joins to participants via `id`.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | int | N | Primary key |
| `event_id` | int | N | FK → events.id |
| `match_order` | int | Y | Position on the card (1 = opener, higher = later) |
| `match_type` | text | Y | `singles`, `tag_team`, `triple_threat`, `fatal_four_way`, `royal_rumble`, `ladder`, `cage`, etc. |
| `stipulation` | text | Y | Special rules (`No DQ`, `Hell in a Cell`, `2 out of 3 falls`) |
| `duration_seconds` | int | Y | Match length where recorded |
| `title_match` | bool | Y | True if a championship is on the line |
| `rating` | float | Y | Cagematch user crowd rating, 0.00 to 10.00. **Real human signal — not scripted.** |
| `cagematch_id` | int | Y | Cagematch.net's match ID |
| `created_at` | timestamp | N | Row insertion |
| `updated_at` | timestamp | N | Last update |

**Notes:**
- `rating` is the only column that's **not a writer's decision** — it's how viewers actually felt about the match. Useful as a target variable for regression problems.
- ~20% of rows have a non-null `rating`; coverage is best for PPV / weekly-TV singles matches and worst for territory-era house shows.

---

## 6. `match_participants` (731,133 rows)

The fact table. One row per (match, wrestler). **`result` is the label** for outcome prediction.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | int | N | Primary key |
| `match_id` | int | N | FK → matches.id |
| `wrestler_id` | int | N | FK → wrestlers.id |
| `team_number` | int | Y | Team grouping for tag/multi-person matches; same number = same side |
| `result` | text | N | `win`, `loss`, `draw`, `dq` (disqualification), `no_contest`, `countout` |
| `entry_order` | int | Y | Entry position for Royal Rumble / battle royal style matches |
| `elimination_order` | int | Y | Order eliminated in multi-person matches (null if not eliminated) |
| `created_at` | timestamp | N | Row insertion |

**Notes:**
- For singles matches there are exactly 2 rows; for tag/multi there can be many.
- The label distribution: ~46% `win`, ~46% `loss`, ~3% `draw/dq/no_contest/countout` combined. Most ML pipelines filter to `win`/`loss` only.
- **Kayfabe warning:** `result` records the booked outcome, not athletic ability.

---

## 7. `titles` (121 rows)

Championship belts.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | int | N | Primary key |
| `name` | text | N | Title name (e.g., "WWE Championship") |
| `promotion_id` | int | N | FK → promotions.id |
| `established` | date | Y | First-awarded date |
| `retired` | date | Y | Date retired/unified (null if active) |
| `active` | bool | N | Whether the title is currently defended |
| `created_at` | timestamp | N | Row insertion |
| `updated_at` | timestamp | N | Last update |

---

## 8. `title_reigns` (1,753 rows)

Reign-level history of championship holders.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | int | N | Primary key |
| `title_id` | int | N | FK → titles.id |
| `wrestler_id` | int | N | FK → wrestlers.id |
| `won_date` | date | N | Date title was won |
| `lost_date` | date | Y | Date lost (null if current reign) |
| `defenses` | int | Y | Number of recorded defenses during the reign |
| `won_at_event_id` | int | Y | FK → events.id (event where reign began) |
| `lost_at_event_id` | int | Y | FK → events.id (event where reign ended) |
| `created_at` | timestamp | N | Row insertion |
| `updated_at` | timestamp | N | Last update |

**Notes:** `defenses` is conservatively counted — only matches explicitly tagged as title defenses in source data.

---

## 9. `alignment_turns` (631 rows)

Face/heel/tweener transitions per wrestler.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | int | N | Primary key |
| `wrestler_id` | int | N | FK → wrestlers.id |
| `from_alignment` | text | Y | Previous alignment (`face`, `heel`, `tweener`, null) |
| `to_alignment` | text | N | New alignment after the turn |
| `turn_date` | date | N | Approximate date of the turn |
| `event_id` | int | Y | FK → events.id (event where turn happened, if pinpointable) |
| `description` | text | Y | Storyline context ("turned heel after attacking former tag partner") |
| `source` | text | Y | `cagematch`, `manual`, `derived` |
| `created_at` | timestamp | N | Row insertion |

**Notes:** Coverage is sparse (~631 turns vs. 12.8K wrestlers); only well-documented turns are recorded.

---

## 10. `match_view.parquet` (denormalized, 731K rows)

Pre-joined ML-ready table. **No SQL joins required** to use this for outcome prediction.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `match_id` | int | N | FK → matches.id |
| `wrestler_id` | int | N | FK → wrestlers.id |
| `ring_name` | text | N | Wrestler's canonical ring name |
| `event_id` | int | N | FK → events.id |
| `event_date` | date | N | Date of the match |
| `year` | int | N | Year extracted from event_date |
| `event_type` | text | Y | PPV/TV/etc. |
| `promotion_id` | int | N | FK → promotions.id |
| `promotion_abbr` | text | N | `WWE`, `AEW`, etc. |
| `match_type` | text | Y | Match format |
| `stipulation` | text | Y | Special rules |
| `title_match` | bool | Y | Title on the line |
| `duration_seconds` | int | Y | Match length |
| `rating` | float | Y | Cagematch crowd rating |
| `team_number` | int | Y | Team grouping |
| `entry_order` | int | Y | Royal Rumble entry |
| `elimination_order` | int | Y | Multi-person elimination order |
| `result` | text | N | **The label** — `win`/`loss`/`draw`/`dq`/`no_contest`/`countout` |
| `n_participants` | int | N | Total wrestlers in this match |
| `n_teams` | int | N | Distinct team_numbers in this match |
| `is_singles` | bool | N | True if `n_participants == 2` and `n_teams == 2` |

**When to use:** Prefer `match_view` for outcome modeling; prefer the source tables when you need full schema fidelity (aliases, alignments, title context).

---

## 11. `feature_matrix.parquet` (~480K rows, model-reproducible)

The 35-feature ML-ready matrix used by the trained `xgboost.joblib` model. Lets users reproduce model predictions without rebuilding the feature pipeline.

**Identifier columns:**

| Column | Type | Description |
|---|---|---|
| `match_id` | int | FK → matches.id |
| `wrestler_id` | int | FK → wrestlers.id |
| `event_date` | date | Match date — use for temporal splits |
| `is_win` | int | Binary label (1 = win, 0 = loss) |

**The 35 features** (grouped by family):

**Win momentum (5):**
- `win_rate_30d`, `win_rate_90d`, `win_rate_365d` — rolling win rates
- `current_win_streak`, `current_loss_streak`

**Event context (4):**
- `is_ppv`, `is_title_match`, `card_position` (1=opener), `event_tier`

**Match type (9):**
- `match_type_win_rate` — wrestler's win rate in this match type
- `is_singles`, `is_tag_team`, `is_triple_threat`, `is_fatal_four_way`
- `is_ladder`, `is_cage`, `is_hell_in_a_cell`, `is_royal_rumble`

**Title proximity (3):**
- `is_champion`, `num_defenses`, `days_since_title_match`

**Career phase (3):**
- `years_active`, `matches_last_90d`, `days_since_last_match`

**Promotion (1):**
- `promotion_win_rate`

**Head-to-head (2):**
- `h2h_win_rate`, `h2h_matches`

**Alignment (6):**
- `alignment` (categorical: face/heel/tweener)
- `is_face`, `is_heel`
- `days_since_turn`, `turns_12m`, `face_heel_matchup`

**Match quality (1):**
- `avg_match_rating` — wrestler's career-average Cagematch rating

**Card position momentum (1):**
- `card_position_momentum` — trend in main-event vs. opener placement

**Important:** All features are computed at *pre-match time* — no future data leakage. Computed by `ml/features.py` against the same Postgres schema used during training.

---

## CSV vs. Parquet — what changes

CSV mirrors of all the above tables are provided for portability. Differences to be aware of:

| Concern | Parquet | CSV |
|---|---|---|
| Type preservation | Yes (date, int, bool, float, text) | No — everything is a string |
| Nulls | Native `NULL` | Empty string |
| Booleans | `True`/`False` | `True`/`False` strings |
| Date parsing | Already `datetime64[ns]` | You must `pd.to_datetime(...)` |
| Compression | snappy (in-file) | None (Kaggle adds zip on upload) |
| Size on disk | 5–10× smaller | Larger but human-readable |

**Recommendation:** Use parquet for analysis; use CSV only if your environment lacks `pyarrow`/`fastparquet`.

---

## Provenance

Sources:
- **Cagematch.net** (public HTML scrape, non-commercial use): bulk of post-1990 data
- **alexdiresta/all-wwe-and-wwf-matches** Kaggle dataset (profightdb dump): cross-validation + pre-1990 coverage

Normalization performed by the ETL pipeline at `github.com/tedrubin80/wrastlingfirst`.
