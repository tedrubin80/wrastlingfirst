# Model Card — Ringside Analytics Match Winner Prediction

**Last trained:** 2026-03-08
**Best model:** XGBoost (`xgboost.joblib`)
**Baseline:** Logistic Regression (`logistic_regression.joblib`)

## Intended use

Predict the probability that a given wrestler wins a match, given pre-match
features about both wrestlers and the match context. Intended for:

- Entertainment and analytical use on the Ringside Analytics site
- Showing predicted win probabilities alongside head-to-head histories
- Research / exploration of feature importance in pro wrestling outcomes

**Not intended for:** betting, gambling advice, or any wagering decision. Pro
wrestling outcomes are scripted; this model learns booking patterns, not
athletic performance.

## Training data

- ~197K historical matches aggregated from public sources (Kaggle datasets
  + Cagematch.net scrape + AEW event imports)
- Coverage: 1980–present across WWE, WCW, ECW, AEW, NXT, TNA
- Label: binary winner for the primary singles competitor, with multi-competitor
  matches reduced to the focal wrestler's outcome

## Features (35 total)

Grouped into seven families:

| Family | Examples |
|---|---|
| Recent form | `current_win_streak`, `current_loss_streak`, `win_rate_30d/90d/365d` |
| Head-to-head | `h2h_win_rate`, `h2h_matches_count` |
| Match context | `is_title_match`, `is_royal_rumble`, `is_singles`, `match_type_win_rate` |
| Status | `is_champion`, `card_position`, `days_since_last_match` |
| Alignment | heel / face / tweener flags at match time |
| Ratings | Cagematch/aggregate crowd ratings, rolling averages |
| Card momentum | recent card-level win share, PPV vs. weekly indicator |

## Performance

| Model | Split | Accuracy | AUC-ROC | Log loss |
|---|---|---:|---:|---:|
| XGBoost | validation | 0.864 | 0.952 | 0.276 |
| XGBoost | **test** | **0.662** | **0.718** | **0.636** |
| Logistic Regression | validation | 0.802 | 0.872 | 0.465 |
| Logistic Regression | test | 0.643 | 0.698 | 0.646 |

**Test-set metrics are the honest ones.** The large validation→test gap
(AUC 0.95 → 0.72) indicates overfitting on the validation fold — likely because
temporally adjacent matches share wrestlers and booking arcs. Treat any single
prediction as weakly informative; the model's edge over the naive "favorite
wins" baseline is real but modest.

### Top XGBoost feature importances

1. `current_win_streak` (0.31)
2. `current_loss_streak` (0.22)
3. `days_since_last_match` (0.13)
4. `h2h_win_rate` (0.09)
5. `is_royal_rumble` (0.03)

Booking momentum (streaks) dominates. Head-to-head history matters. Match
type is a weak signal except for battle-royal-style matches where winner
distribution is highly non-uniform.

## Limitations & biases

- **Selection bias toward televised matches.** House-show and indie results are
  sparsely represented; model generalizes best to PPV / weekly-TV singles.
- **Kayfabe is not athletic skill.** The model learns who tends to be booked
  to win, not who would win a real fight. Storyline context (face/heel turns,
  upcoming PPV) drives outcomes more than measurable ability.
- **Gender imbalance.** Women's division sample size is smaller; expect wider
  confidence intervals for women's matches.
- **Era drift.** A 1987 Hogan match and a 2025 Cody match sit in the same
  training set. Temporal splits help but booking philosophy changes across
  eras are not fully modeled.
- **Data recency.** Retraining runs nightly via the refresh job; a model loaded
  from disk may be up to 24h stale.

## How the model is served

- Trained artifact: `ml/models/xgboost.joblib` + `scaler.joblib`
- Served via FastAPI (`ml/service/`) behind the Express API
- Features computed at request time from PostgreSQL against the same SQL views
  used during training (parity fix: commit `9545bf1`)

## Retraining

```bash
make train          # re-runs ml/train.py, regenerates models + training_report.json
```

Update this card whenever the feature set or training data changes
materially. The numbers above are auto-derivable from
`ml/models/training_report.json`.

## License & attribution

Data sourced from public Kaggle datasets and Cagematch.net (non-commercial).
Model weights are project-internal; no redistribution of training data.
