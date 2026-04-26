"""Ringside Wrestling Archive — Python quickstart.

Run after downloading the dataset from Kaggle/Hugging Face. Loads the parquet
files and answers ten common questions to get you oriented.

Usage
-----
    pip install pandas pyarrow
    python python_quickstart.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

# Adjust to wherever you extracted the dataset
DATA = Path(".")  # <- point this at the directory with the .parquet files

# ─── 1. Load everything ──────────────────────────────────────────────────
TABLES = [
    "promotions", "wrestlers", "wrestler_aliases", "events", "matches",
    "match_participants", "titles", "title_reigns", "alignment_turns",
]
df = {name: pd.read_parquet(DATA / f"{name}.parquet") for name in TABLES}
for name, t in df.items():
    print(f"{name:<22s} {len(t):>10,d} rows")

print()


# ─── 2. Top-10 wrestlers by total matches ────────────────────────────────
top = (
    df["match_participants"]
    .merge(df["wrestlers"][["id", "ring_name"]], left_on="wrestler_id", right_on="id")
    .groupby("ring_name").size().sort_values(ascending=False).head(10)
)
print("Top 10 by match count:")
print(top.to_string())
print()


# ─── 3. Matches per year ────────────────────────────────────────────────
me = df["matches"].merge(
    df["events"][["id", "date"]].rename(columns={"id": "event_id"}),
    on="event_id",
)
me["year"] = pd.to_datetime(me["date"]).dt.year
per_year = me.groupby("year").size()
print(f"Coverage: {per_year.index.min()}–{per_year.index.max()}")
print(f"Peak year: {per_year.idxmax()} ({per_year.max():,} matches)")
print()


# ─── 4. Win-rate distribution (kayfabe demo) ─────────────────────────────
mp = df["match_participants"].copy()
mp["is_win"] = (mp["result"] == "win").astype(int)
career = mp.groupby("wrestler_id").agg(
    matches=("is_win", "size"),
    win_rate=("is_win", "mean"),
).query("matches >= 50")
print(f"Wrestlers with ≥50 matches: {len(career):,}")
print(f"Mean career win rate: {career['win_rate'].mean():.3f}")
print(f"Top 5%: win rate ≥ {career['win_rate'].quantile(0.95):.3f}")
print(f"Bot 5%: win rate ≤ {career['win_rate'].quantile(0.05):.3f}")
print()


# ─── 5. Longest title reigns ────────────────────────────────────────────
tr = df["title_reigns"].copy()
tr["won_date"] = pd.to_datetime(tr["won_date"])
tr["lost_date"] = pd.to_datetime(tr["lost_date"])
tr["length_days"] = (tr["lost_date"].fillna(pd.Timestamp.today()) - tr["won_date"]).dt.days
top_reigns = (
    tr.merge(df["wrestlers"][["id", "ring_name"]], left_on="wrestler_id", right_on="id")
      .merge(df["titles"][["id", "name"]].rename(columns={"id": "title_id", "name": "title"}), on="title_id")
      [["ring_name", "title", "length_days", "won_date"]]
      .sort_values("length_days", ascending=False)
      .head(10)
)
print("Top 10 longest title reigns:")
print(top_reigns.to_string(index=False))
print()


# ─── 6. Match types breakdown ───────────────────────────────────────────
print("Match type distribution:")
print(df["matches"]["match_type"].value_counts().head(10).to_string())
print()


# ─── 7. WWE vs AEW: average match rating ────────────────────────────────
em = df["matches"].merge(df["events"][["id", "promotion_id"]].rename(columns={"id": "event_id"}), on="event_id")
em = em.merge(df["promotions"][["id", "abbreviation"]].rename(columns={"id": "promotion_id"}), on="promotion_id")
print("Average crowd rating (Cagematch) by promotion (where rated):")
print(em.dropna(subset=["rating"]).groupby("abbreviation")["rating"].agg(["mean", "count"]).round(2).to_string())
print()


# ─── 8. Royal Rumble winners ────────────────────────────────────────────
rumbles = df["matches"][df["matches"]["match_type"] == "royal_rumble"]
rumble_wins = (
    df["match_participants"][df["match_participants"]["match_id"].isin(rumbles["id"]) &
                             (df["match_participants"]["result"] == "win")]
    .merge(df["wrestlers"][["id", "ring_name"]], left_on="wrestler_id", right_on="id")
    ["ring_name"].value_counts().head(10)
)
print("Most Royal Rumble wins:")
print(rumble_wins.to_string())
print()


# ─── 9. Singles-only filter for ML ──────────────────────────────────────
singles_match_ids = (
    df["match_participants"].groupby("match_id").size()
    .pipe(lambda s: s[s == 2]).index
)
singles = df["match_participants"][df["match_participants"]["match_id"].isin(singles_match_ids)]
print(f"Singles match participants: {len(singles):,}")
print(f"  ({len(singles_match_ids):,} matches × 2 wrestlers each)")
print()


# ─── 10. Naive baseline classifier (career win rate) ───────────────────
# (For honest evaluation with proper temporal splits, see the trained model:
#  https://www.kaggle.com/models/theodorerubin/ringside-analytics-match-winner)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import train_test_split

s = singles[singles["result"].isin(["win", "loss"])].copy()
s["is_win"] = (s["result"] == "win").astype(int)
career_wr = s.groupby("wrestler_id")["is_win"].mean().rename("career_wr")
career_n = s.groupby("wrestler_id")["is_win"].size().rename("career_n")
X = s.merge(career_wr, left_on="wrestler_id", right_index=True) \
     .merge(career_n, left_on="wrestler_id", right_index=True)[["career_wr", "career_n"]]
y = s["is_win"].values
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42)
clf = LogisticRegression(max_iter=1000).fit(Xtr, ytr)
print(f"Baseline accuracy: {accuracy_score(yte, clf.predict(Xte)):.3f}")
print(f"Baseline AUC:      {roc_auc_score(yte, clf.predict_proba(Xte)[:, 1]):.3f}")
print("(Note: this naive baseline has data leakage — career_wr includes the test rows.")
print(" The trained model uses 35 features and a proper temporal split.)")
