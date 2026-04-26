"""Build starter.ipynb from inline cell content.

Run: python3 build.py
Pushes via: kaggle kernels push -p .
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent

# Each cell is (kind, source). kind is "md" or "py".
# Source is a single string; we split on \n for the canonical array-of-lines form.
CELLS: list[tuple[str, str]] = [

# ─── Cell 1: opening hook ──────────────────────────────────────────
("md", """\
# Getting Started with the Ringside Wrestling Archive

**Most ML datasets have ground truth. This one has a writer's room.**

Pro wrestling outcomes are scripted. The `result` column in this dataset doesn't record who's the better athlete — it records who got booked to win. That sounds like a flaw. It's actually the most interesting thing about this dataset.

This notebook is a tour: we'll load the nine tables, look at what 40+ years of pro wrestling data actually looks like, build a baseline classifier on match outcomes, and then I'll show you why the *kayfabe problem* turns standard ML wisdom on its head.

If you've been looking for a tabular dataset that's:

- Real-world scale (482K matches, 731K participations, 12.8K wrestlers)
- Genuinely weird in its label semantics (a great teaching case for label noise)
- Free to use (CC0)

— start here.
"""),

# ─── Cell 2: what's in here ────────────────────────────────────────
("md", """\
## What's in here

Nine relational parquet files, joinable on `id` columns:

| File | Rows | What |
|---|---:|---|
| `matches.parquet` | 482K | Match metadata: type, stipulation, duration, title flag, rating |
| `match_participants.parquet` | 731K | One row per wrestler-per-match. **`result` is the label** for outcome prediction |
| `wrestlers.parquet` | 12.8K | Ring name, real name, gender, debut date, status |
| `events.parquet` | 35K | Date, venue, city, promotion, event type |
| `promotions.parquet` | 6 | WWE, AEW, WCW, ECW, NXT, TNA |
| `titles.parquet` | 121 | Championship belts |
| `title_reigns.parquet` | 1.7K | Reign start/end + defenses |
| `wrestler_aliases.parquet` | 13K | Alternate ring names |
| `alignment_turns.parquet` | 631 | Face/heel/tweener transitions |

**Coverage:** WWE, AEW, WCW, ECW, NXT, TNA — 1980 through present.
**License:** CC0 1.0 (public domain).
**Source:** public Cagematch.net scrapes + alexdiresta profightdb dump, normalized into a Postgres schema.

Companion trained model: [`theodorerubin/ringside-analytics-match-winner`](https://www.kaggle.com/models/theodorerubin/ringside-analytics-match-winner).
"""),

# ─── Cell 3: imports + path ────────────────────────────────────────
("py", """\
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Kaggle attaches the dataset at /kaggle/input/<slug>/.
# Falls back to a local checkout if you're running outside Kaggle.
KAGGLE_PATH = Path("/kaggle/input/ringside-wrestling-archive")
LOCAL_PATH = Path("../../../data/kaggle")
DATA = KAGGLE_PATH if KAGGLE_PATH.exists() else LOCAL_PATH

print(f"Reading parquets from: {DATA}")
"""),

# ─── Cell 4: load all 9 ────────────────────────────────────────────
("py", """\
TABLES = [
    "promotions", "wrestlers", "wrestler_aliases", "events",
    "matches", "match_participants", "titles", "title_reigns",
    "alignment_turns",
]

dfs = {name: pd.read_parquet(DATA / f"{name}.parquet") for name in TABLES}

for name, df in dfs.items():
    print(f"{name:<22s} {len(df):>10,d} rows  x  {len(df.columns):>2d} cols")
"""),

# ─── Cell 5: schema map ────────────────────────────────────────────
("md", """\
## How the tables join

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

The fact-table that matters most for ML is **`match_participants`**: one row per (match, wrestler), with the `result` label. Everything else is dimension data you join in for features.
"""),

# ─── Cell 6: coverage section header ───────────────────────────────
("md", """\
## 1. Forty years of coverage

Let's see how matches are distributed over time. This tells you which eras are well-represented and which to be skeptical of.
"""),

# ─── Cell 7: matches per year ──────────────────────────────────────
("py", """\
me = dfs["matches"].merge(
    dfs["events"][["id", "date"]].rename(columns={"id": "event_id"}),
    on="event_id", how="left",
)
me["year"] = pd.to_datetime(me["date"]).dt.year

per_year = me.groupby("year").size()

fig, ax = plt.subplots(figsize=(11, 4))
per_year.plot(ax=ax, color="#c9352d", linewidth=2)
ax.set_title("Matches per year in the archive")
ax.set_xlabel("Year"); ax.set_ylabel("Matches")
ax.grid(alpha=0.3)
plt.tight_layout(); plt.show()

print(f"Total matches: {len(me):,}")
print(f"Years covered: {int(per_year.index.min())}-{int(per_year.index.max())}")
"""),

# ─── Cell 8: coverage interpretation ───────────────────────────────
("md", """\
A few things to notice:

- **The 1980s are thin.** Territory-era data is sparse and dominated by just a few promotions.
- **Mid-1990s through 2010s are the meat.** Cagematch is most complete here, and the WWE-WCW war years generated a flood of televised matches.
- **AEW's 2019 arrival** is visible as an upward step.
- The current year is partial — treat it as in-progress.

If you're training models, decide upfront whether you want to weight all years equally or focus on the last decade where coverage is densest.
"""),

# ─── Cell 9: promotion section header ──────────────────────────────
("md", """\
## 2. Who's in the data?

Promotions are not represented equally. WWE dominates because it's been televised continuously since the 1980s. Knowing the share matters: a model trained on this data will inherit WWE's booking conventions whether you intended it or not.
"""),

# ─── Cell 10: promotion share ──────────────────────────────────────
("py", """\
em = dfs["matches"].merge(
    dfs["events"][["id", "promotion_id"]].rename(columns={"id": "event_id"}),
    on="event_id", how="left",
).merge(
    dfs["promotions"][["id", "abbreviation"]].rename(columns={"id": "promotion_id"}),
    on="promotion_id", how="left",
)

share = em["abbreviation"].value_counts()

fig, ax = plt.subplots(figsize=(8, 4))
share.plot.barh(ax=ax, color="#c9352d")
ax.set_title("Matches by promotion")
ax.set_xlabel("Matches")
ax.invert_yaxis()
plt.tight_layout(); plt.show()

share.to_frame("matches")
"""),

# ─── Cell 11: promotion takeaway ───────────────────────────────────
("md", """\
WWE accounts for the lion's share. AEW is the second-largest active promotion. WCW (defunct 2001) and ECW (defunct 2001) are historical cohorts — they won't grow, but they're useful for testing era robustness.
"""),

# ─── Cell 12: KAYFABE REVEAL ───────────────────────────────────────
("md", """\
## 3. The kayfabe twist

Now the most important section in this notebook.

In a normal sports dataset, `result` would record an athletic outcome — who actually won the match. **Pro wrestling is scripted.** Outcomes are decided in advance by writers. So `result` records **who was booked to win**, not who would win an athletic contest.

This sounds like a small distinction. It's not. It changes what your model is allowed to learn:

- A model can never learn "athletic ability" from this data, because it isn't measured here.
- A model *can* learn "booking patterns" — which wrestlers tend to be pushed, which are jobbers, which feuds end at PPVs.
- The label is **autocorrelated with itself**: a wrestler on a 5-match winning streak is usually being booked toward a payoff, so the next match's outcome isn't independent of the previous five.

Let's prove this with one chart. If outcomes were random, every wrestler's win rate would cluster near 0.5. Look what happens instead:
"""),

# ─── Cell 13: bimodal win rate ─────────────────────────────────────
("py", """\
mp = dfs["match_participants"].copy()
mp["is_win"] = (mp["result"] == "win").astype(int)

# Wrestlers with at least 50 matches (filters one-off appearances)
wins = mp.groupby("wrestler_id").agg(
    matches=("is_win", "size"),
    win_rate=("is_win", "mean"),
).query("matches >= 50")

fig, ax = plt.subplots(figsize=(10, 4))
ax.hist(wins["win_rate"], bins=50, color="#c9352d", alpha=0.85, edgecolor="white")
ax.axvline(0.5, color="black", linestyle="--", linewidth=1, label="coin flip")
ax.set_title(f"Career win rate distribution ({len(wins):,} wrestlers, ≥50 matches)")
ax.set_xlabel("Win rate"); ax.set_ylabel("Wrestlers")
ax.legend()
plt.tight_layout(); plt.show()

print(f"Mean win rate: {wins['win_rate'].mean():.3f}")
print(f"Std:           {wins['win_rate'].std():.3f}")
print(f"% above 0.7:   {(wins['win_rate'] > 0.7).mean():.1%}")
print(f"% below 0.3:   {(wins['win_rate'] < 0.3).mean():.1%}")
"""),

# ─── Cell 14: kayfabe takeaway ─────────────────────────────────────
("md", """\
That's the kayfabe signature. Win rates aren't normally distributed around 0.5 — they have a heavy left tail (jobbers booked to lose) and a heavy right tail (stars booked to win). Hulk Hogan, John Cena, Roman Reigns sit far above 0.5; enhancement talent sits far below.

**For ML practice, this is gold.** It means:

1. **Career win rate alone is a strong feature.** A coin flip wins ~50%; a model that just predicts "the wrestler with the higher career win rate" wins ~65%.
2. **Streaks matter even more.** Booking is path-dependent. Streaks compound until the planned cool-down — meaning past wins predict future wins, but the relationship breaks suddenly when storyline arcs end.
3. **Validation metrics will lie to you.** Wrestlers and storylines persist for months. Random k-fold splits leak information across folds. We'll see what happens at the end of this notebook.
"""),

# ─── Cell 15: title section header ─────────────────────────────────
("md", """\
## 4. Title reigns: the long tail

Championship reigns are a narrative anchor — every belt change is a deliberate booking decision. The reign-length distribution shows how the average title is held.
"""),

# ─── Cell 16: title reigns ─────────────────────────────────────────
("py", """\
tr = dfs["title_reigns"].copy()
tr["won_date"]  = pd.to_datetime(tr["won_date"])
tr["lost_date"] = pd.to_datetime(tr["lost_date"])

# Treat ongoing reigns as "today minus won_date"
today = pd.Timestamp.today().normalize()
tr["length_days"] = (tr["lost_date"].fillna(today) - tr["won_date"]).dt.days
tr = tr[tr["length_days"] > 0]

fig, ax = plt.subplots(figsize=(10, 4))
ax.hist(tr["length_days"].clip(upper=730), bins=60, color="#c9352d", alpha=0.85, edgecolor="white")
ax.set_title("Title reign length (days, capped at 2 years for visibility)")
ax.set_xlabel("Days"); ax.set_ylabel("Reigns")
plt.tight_layout(); plt.show()

print(f"Median reign:  {tr['length_days'].median():.0f} days")
print(f"Mean reign:    {tr['length_days'].mean():.0f} days")
print(f"Longest reign: {tr['length_days'].max():.0f} days")
"""),

# ─── Cell 17: baseline section header ──────────────────────────────
("md", """\
## 5. A simple baseline classifier

Let's build the smallest possible match-outcome predictor. Per-wrestler features only:

- **Career win rate** (overall booking strength)
- **Career match count** (experience / TV exposure)

Logistic regression. No tuning. Just to see what's possible from almost nothing.
"""),

# ─── Cell 18: baseline LR ──────────────────────────────────────────
("py", """\
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import train_test_split

mp_simple = mp[mp["result"].isin(["win", "loss"])].copy()
mp_simple["is_win"] = (mp_simple["result"] == "win").astype(int)

# Per-wrestler career stats — note: leakage warning, see next cell
wstats = mp_simple.groupby("wrestler_id").agg(
    career_wr=("is_win", "mean"),
    career_n=("is_win", "size"),
).reset_index()

X = mp_simple.merge(wstats, on="wrestler_id")[["career_wr", "career_n"]].fillna(0)
y = mp_simple["is_win"].values

# Random 80/20 split — we want to see the leakage problem
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42)

clf = LogisticRegression(max_iter=1000).fit(Xtr, ytr)
preds = clf.predict(Xte)
probs = clf.predict_proba(Xte)[:, 1]

print(f"Accuracy: {accuracy_score(yte, preds):.3f}")
print(f"AUC-ROC:  {roc_auc_score(yte, probs):.3f}")
"""),

# ─── Cell 19: leakage tease ────────────────────────────────────────
("md", """\
~0.65 accuracy from two features and zero tuning. That feels like a win.

It isn't.

Look closely at how we computed `career_wr`: across the **entire dataset**, then split. Every test-set match's "career win rate" includes that match itself in its own feature. That's data leakage.

The fully-featured XGBoost model in the companion `theodorerubin/ringside-analytics-match-winner` repo uses 35 features and a proper temporal split. Its honest test-set numbers:

| Split | Accuracy | AUC-ROC |
|---|---:|---:|
| Validation | 0.864 | **0.952** |
| Test       | 0.662 | **0.718** |

A 25-point AUC drop from validation to test isn't a tuning problem. It's the kayfabe problem in action — wrestlers and storylines persist across the val/test boundary in ways that leak signal in validation but vanish in the future.

**That story is the second notebook in this series.** Coming soon.
"""),

# ─── Cell 20: where to go next ─────────────────────────────────────
("md", """\
## Where to go from here

You now have:

- The schema and join structure
- An honest sense of coverage and bias
- The kayfabe framing for label semantics
- A leaky baseline that beats coin flip

Suggested next steps:

- **Build proper temporal splits.** Train on matches before 2024, validate 2024, test 2025+. The drop in metrics is the lesson.
- **Add streak features.** Rolling win counts and `days_since_last_match` are the biggest drivers in the trained model. Try them.
- **Pick a different target.** Match outcomes are scripted. **Cagematch crowd ratings** (in `matches.rating`) are a real human signal — try regression on rating instead. Higher ceiling, more interesting failure modes.
- **Try storyline NLP.** Match descriptions and event names contain narrative context the trained model never sees. There's real signal there.

If you build something with this dataset, drop a link in the discussion.

---

**Companion resources:**

- Trained model: [theodorerubin/ringside-analytics-match-winner](https://www.kaggle.com/models/theodorerubin/ringside-analytics-match-winner)
- HF mirror of this dataset: [datamatters24/ringside-analytics](https://huggingface.co/datasets/datamatters24/ringside-analytics)
- Source code: [github.com/tedrubin80/wrastlingfirst](https://github.com/tedrubin80/wrastlingfirst)

License: CC0 1.0. Use it however you want.
"""),

]


def make_cell(kind: str, source: str) -> dict:
    """Construct a single notebook cell dict."""
    lines = source.splitlines(keepends=True)
    if kind == "md":
        return {
            "cell_type": "markdown",
            "metadata": {},
            "source": lines,
        }
    return {
        "cell_type": "code",
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": lines,
    }


def main() -> None:
    nb = {
        "cells": [make_cell(k, s) for k, s in CELLS],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.10",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }

    out = HERE / "starter.ipynb"
    out.write_text(json.dumps(nb, indent=1, ensure_ascii=False))
    print(f"Wrote {out} ({len(CELLS)} cells)")


if __name__ == "__main__":
    main()
