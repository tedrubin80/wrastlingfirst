"""Push trained Ringside Analytics model to Hugging Face Hub.

Usage
-----
    HF_TOKEN=$(cat ~/.cache/huggingface/token) python3 push_hf_model.py

Creates / updates `datamatters24/ringside-match-winner` model repo.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from huggingface_hub import HfApi, create_repo

REPO_ID = "datamatters24/ringside-match-winner"
ML_DIR = Path(__file__).parent.parent
MODELS_DIR = ML_DIR / "models"

# Feature columns must match ml/features.py exactly. Keep this in sync.
FEATURE_COLUMNS = [
    # Win momentum (5)
    "win_rate_30d", "win_rate_90d", "win_rate_365d",
    "current_win_streak", "current_loss_streak",
    # Event context (4)
    "is_ppv", "is_title_match", "card_position", "event_tier",
    # Match type (9)
    "match_type_win_rate",
    "is_singles", "is_tag_team", "is_triple_threat", "is_fatal_four_way",
    "is_ladder", "is_cage", "is_hell_in_a_cell", "is_royal_rumble",
    # Title proximity (3)
    "is_champion", "num_defenses", "days_since_title_match",
    # Career phase (3)
    "years_active", "matches_last_90d", "days_since_last_match",
    # Promotion (1)
    "promotion_win_rate",
    # Head-to-head (2)
    "h2h_win_rate", "h2h_matches",
    # Alignment (6)
    "alignment", "is_face", "is_heel",
    "days_since_turn", "turns_12m", "face_heel_matchup",
    # Match quality (1)
    "avg_match_rating",
    # Card position momentum (1)
    "card_position_momentum",
]

# Feature columns saved next to the model so users know what to feed in
FEATURE_COLUMNS_JSON = json.dumps(
    {
        "feature_columns": FEATURE_COLUMNS,
        "n_features": len(FEATURE_COLUMNS),
        "target": "is_win",
        "scaler": "scaler.joblib (StandardScaler)",
        "primary_model": "xgboost.joblib",
        "baseline_model": "logistic_regression.joblib",
    },
    indent=2,
)

MODEL_CARD = """\
---
license: apache-2.0
library_name: scikit-learn
tags:
  - tabular-classification
  - sports
  - wrestling
  - xgboost
  - sklearn
  - kayfabe
language:
  - en
datasets:
  - datamatters24/ringside-analytics
  - theodorerubin/ringside-wrestling-archive
metrics:
  - accuracy
  - roc_auc
  - log_loss
model-index:
  - name: ringside-match-winner
    results:
      - task:
          type: tabular-classification
          name: Pro wrestling match outcome prediction
        dataset:
          name: Ringside Analytics Wrestling Archive
          type: datamatters24/ringside-analytics
        metrics:
          - type: accuracy
            value: 0.662
            name: Test accuracy
          - type: roc_auc
            value: 0.718
            name: Test AUC-ROC
          - type: log_loss
            value: 0.636
            name: Test log loss
---

# Ringside Analytics — Match Winner Predictor

Predicts the probability that a given pro wrestler wins a match, given
pre-match state about both wrestlers and the match context.

**XGBoost** is the primary model (`xgboost.joblib`). A logistic-regression
baseline is included for reference (`logistic_regression.joblib`). Both share
the `StandardScaler` in `scaler.joblib` and the 35 features listed in
`feature_columns.json`.

## ⚠️ Important framing — the kayfabe problem

Pro wrestling outcomes are **scripted**. The training label records the booked
outcome (who the writers decided wins), not athletic ability. This model
therefore learns **booking patterns**, not skill. It is not, and cannot be,
useful for betting.

The companion paper at <https://tedrubin80.github.io/wrastlingfirst/paper.html>
walks through what this means for ML practice — particularly why the
validation→test AUC gap of 25 points (0.952 → 0.718) is structural rather than
a methodological error.

## Performance (test set — the honest numbers)

| Model | Accuracy | AUC-ROC | Log loss |
|---|---:|---:|---:|
| **XGBoost** | **0.662** | **0.718** | **0.636** |
| Logistic Regression | 0.643 | 0.698 | 0.646 |

Coin-flip baseline: 0.500 AUC. "Favored wrestler always wins" baseline: ~0.62 AUC.

## Top feature importances (XGBoost)

1. `current_win_streak` (0.31)
2. `current_loss_streak` (0.22)
3. `days_since_last_match` (0.13)
4. `h2h_win_rate` (0.09)
5. `is_royal_rumble` (0.03)

Booking momentum (streaks) carries over half the model's signal. Removing the
streak family in ablation drops test AUC to 0.541 — barely above coin-flip.

## Quickstart

```python
import joblib
import pandas as pd

# Download artifacts
from huggingface_hub import hf_hub_download

xgb_path    = hf_hub_download(repo_id="datamatters24/ringside-match-winner", filename="xgboost.joblib")
scaler_path = hf_hub_download(repo_id="datamatters24/ringside-match-winner", filename="scaler.joblib")

xgb    = joblib.load(xgb_path)
scaler = joblib.load(scaler_path)

# X must be a DataFrame with exactly the 35 feature columns from feature_columns.json
# Reproduce feature engineering: see https://github.com/tedrubin80/wrastlingfirst/blob/main/ml/features.py
# Or use the prebuilt feature_matrix.parquet from the dataset:
# https://huggingface.co/datasets/datamatters24/ringside-analytics

X_scaled = scaler.transform(X)
proba = xgb.predict_proba(X_scaled)[:, 1]    # P(win)
```

## How to reproduce predictions exactly

The dataset bundles `feature_matrix.parquet` — the exact 35-feature snapshot
used at training time. Loading that file and running the model gives identical
predictions to the served version.

```python
import pandas as pd, joblib
from huggingface_hub import hf_hub_download

fm_path = hf_hub_download(
    repo_id="datamatters24/ringside-analytics",
    repo_type="dataset",
    filename="feature_matrix.parquet",
)
fm = pd.read_parquet(fm_path)

# (Optional) honest temporal split
fm["event_date"] = pd.to_datetime(fm["event_date"])
test = fm[fm["event_date"] >= "2025-01-01"]
```

## Limitations

- **Selection bias toward televised matches.** House-show / indie data is sparse.
- **Kayfabe is not athletic skill.** The model learns booking, not ability.
- **Era drift.** Booking philosophy has shifted over 40+ years; the model averages across eras.
- **Gender imbalance.** Women's-division sample is smaller; expect wider error bars.
- **Single predictions are weakly informative.** AUC 0.72 means meaningful lift over coin-flip but not betting-grade calibration.

## Companion resources

- 📊 **Dataset (HF):** [datamatters24/ringside-analytics](https://huggingface.co/datasets/datamatters24/ringside-analytics)
- 📊 **Dataset (Kaggle):** [theodorerubin/ringside-wrestling-archive](https://www.kaggle.com/datasets/theodorerubin/ringside-wrestling-archive)
- 🎰 **Kaggle Model:** [theodorerubin/ringside-analytics-match-winner](https://www.kaggle.com/models/theodorerubin/ringside-analytics-match-winner) (mirror)
- 📝 **Paper / portfolio:** [tedrubin80.github.io/wrastlingfirst](https://tedrubin80.github.io/wrastlingfirst/)
- 💻 **Source code:** [github.com/tedrubin80/wrastlingfirst](https://github.com/tedrubin80/wrastlingfirst)

## Citation

```bibtex
@misc{rubin2026ringside,
  author = {Rubin, Theodore},
  title  = {Ringside Analytics: Match Winner Predictor},
  year   = {2026},
  url    = {https://huggingface.co/datamatters24/ringside-match-winner}
}
```

## License

Apache 2.0 (model weights). Training data: CC0 (see linked dataset).
"""


def main() -> int:
    api = HfApi()  # picks up HF_TOKEN from env or ~/.cache/huggingface/token

    print(f"Creating repo {REPO_ID} (or no-op if exists)...")
    create_repo(REPO_ID, repo_type="model", exist_ok=True, private=False)

    # Write README.md and feature_columns.json into a temp staging dir to upload as a folder
    import tempfile, shutil
    with tempfile.TemporaryDirectory() as staging:
        staging = Path(staging)

        # README (model card)
        (staging / "README.md").write_text(MODEL_CARD)

        # Feature columns reference
        (staging / "feature_columns.json").write_text(FEATURE_COLUMNS_JSON)

        # Model artifacts
        for fname in ("xgboost.joblib", "logistic_regression.joblib", "scaler.joblib", "training_report.json"):
            src = MODELS_DIR / fname
            if src.exists():
                shutil.copy2(src, staging / fname)
                print(f"  staged {fname} ({src.stat().st_size / 1024:.0f} KB)")
            else:
                print(f"  WARNING: {fname} missing")

        print(f"\nUploading to {REPO_ID} ...")
        api.upload_folder(
            folder_path=str(staging),
            repo_id=REPO_ID,
            repo_type="model",
            commit_message="Initial public release — XGBoost + LR baseline + scaler + model card",
        )
        print(f"Done. https://huggingface.co/{REPO_ID}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
