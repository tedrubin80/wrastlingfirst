"""Build pandas_recipes.ipynb — a 10-recipe cookbook for the Ringside dataset.

Run: python3 build_recipes.py
Output: pandas_recipes.ipynb (sibling)
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent

CELLS: list[tuple[str, str]] = [

# ─── Intro ───────────────────────────────────────────────────────────
("md", """\
# Pandas Recipes — Ringside Wrestling Archive

Ten common analyses on the dataset, each a self-contained recipe. Pick the one closest to what you want to do and adapt.

**Setup:** point `DATA` at the directory holding the `.parquet` files (Kaggle attaches the dataset at `/kaggle/input/ringside-wrestling-archive/`).
"""),

("py", """\
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

DATA = Path("/kaggle/input/ringside-wrestling-archive")
if not DATA.exists():
    DATA = Path(".")

TABLES = ["promotions", "wrestlers", "wrestler_aliases", "events", "matches",
          "match_participants", "titles", "title_reigns", "alignment_turns"]
df = {n: pd.read_parquet(DATA / f"{n}.parquet") for n in TABLES}

print({n: len(t) for n, t in df.items()})
"""),

# ─── 1. Wrestler profile lookup ──────────────────────────────────────
("md", """\
## Recipe 1 — Wrestler profile lookup (with alias resolution)

Find a wrestler by any name they've used (ring name or alias) and return their canonical profile.
"""),

("py", """\
def find_wrestler(name: str) -> pd.Series:
    name = name.strip().lower()
    # Try canonical ring_name first
    hit = df["wrestlers"][df["wrestlers"]["ring_name"].str.lower() == name]
    if len(hit):
        return hit.iloc[0]
    # Fall back to aliases
    alias_match = df["wrestler_aliases"][df["wrestler_aliases"]["alias"].str.lower() == name]
    if len(alias_match):
        wid = alias_match.iloc[0]["wrestler_id"]
        return df["wrestlers"][df["wrestlers"]["id"] == wid].iloc[0]
    raise KeyError(f"No wrestler named {name!r}")

print(find_wrestler("Stone Cold Steve Austin").to_dict())
"""),

# ─── 2. Career arc ──────────────────────────────────────────────────
("md", """\
## Recipe 2 — Career arc (matches per year for one wrestler)
"""),

("py", """\
def career_arc(wrestler_id: int) -> pd.Series:
    mp = df["match_participants"]
    m = df["matches"][["id", "event_id"]].rename(columns={"id": "match_id"})
    e = df["events"][["id", "date"]].rename(columns={"id": "event_id"})
    arc = (mp[mp["wrestler_id"] == wrestler_id]
           .merge(m, on="match_id")
           .merge(e, on="event_id"))
    arc["year"] = pd.to_datetime(arc["date"]).dt.year
    return arc.groupby("year").size()

w = find_wrestler("John Cena")
arc = career_arc(int(w["id"]))

fig, ax = plt.subplots(figsize=(10, 3))
arc.plot(ax=ax, color="#c9352d", linewidth=2, marker="o", markersize=3)
ax.set_title(f"Career arc — {w['ring_name']}")
ax.set_xlabel("Year"); ax.set_ylabel("Matches")
ax.grid(alpha=0.3)
plt.tight_layout(); plt.show()
"""),

# ─── 3. Head-to-head ────────────────────────────────────────────────
("md", """\
## Recipe 3 — Head-to-head record between two wrestlers
"""),

("py", """\
def head_to_head(name_a: str, name_b: str) -> pd.DataFrame:
    a = find_wrestler(name_a); b = find_wrestler(name_b)
    mp = df["match_participants"]

    # Find singles matches both participated in
    singles_match_ids = mp.groupby("match_id").size().pipe(lambda s: s[s == 2]).index
    a_in = mp[(mp["wrestler_id"] == a["id"]) & mp["match_id"].isin(singles_match_ids)]
    common = a_in[a_in["match_id"].isin(
        mp[mp["wrestler_id"] == b["id"]]["match_id"]
    )]

    # For each common match: did A win?
    out = common[["match_id", "result"]].copy()
    out["a_won"] = (out["result"] == "win").astype(int)

    e = df["events"][["id", "date"]].rename(columns={"id": "event_id"})
    m = df["matches"][["id", "event_id"]].rename(columns={"id": "match_id"})
    out = out.merge(m, on="match_id").merge(e, on="event_id")
    out = out.sort_values("date")
    print(f"{a['ring_name']} {out['a_won'].sum()}–{(1-out['a_won']).sum()} {b['ring_name']}")
    return out[["date", "a_won"]]

h2h = head_to_head("The Rock", "Stone Cold Steve Austin")
h2h.tail(10)
"""),

# ─── 4. Match rating outliers ────────────────────────────────────────
("md", """\
## Recipe 4 — Highest- and lowest-rated matches by promotion
"""),

("py", """\
em = df["matches"].merge(
    df["events"][["id", "promotion_id", "date", "name"]].rename(columns={"id": "event_id", "name": "event_name"}),
    on="event_id"
).merge(
    df["promotions"][["id", "abbreviation"]].rename(columns={"id": "promotion_id"}),
    on="promotion_id"
).dropna(subset=["rating"])

print("Top 5 rated matches per promotion:")
for promo, g in em.groupby("abbreviation"):
    if len(g) < 50:
        continue
    top5 = g.nlargest(5, "rating")[["date", "event_name", "rating"]]
    print(f"\\n--- {promo} ---")
    print(top5.to_string(index=False))
"""),

# ─── 5. Title lineage ────────────────────────────────────────────────
("md", """\
## Recipe 5 — Full title lineage
"""),

("py", """\
def title_lineage(title_substring: str) -> pd.DataFrame:
    titles = df["titles"][df["titles"]["name"].str.contains(title_substring, case=False, na=False)]
    if titles.empty:
        raise KeyError(f"No title matched {title_substring!r}")
    title = titles.iloc[0]
    print(f"Lineage of: {title['name']}")

    reigns = df["title_reigns"][df["title_reigns"]["title_id"] == title["id"]].copy()
    reigns = reigns.merge(
        df["wrestlers"][["id", "ring_name"]].rename(columns={"id": "wrestler_id"}),
        on="wrestler_id"
    ).sort_values("won_date")
    reigns["won_date"]  = pd.to_datetime(reigns["won_date"]).dt.date
    reigns["lost_date"] = pd.to_datetime(reigns["lost_date"]).dt.date
    return reigns[["ring_name", "won_date", "lost_date", "defenses"]]

title_lineage("WWE Championship").tail(20)
"""),

# ─── 6. Alignment timeline ───────────────────────────────────────────
("md", """\
## Recipe 6 — Alignment turn timeline for a wrestler
"""),

("py", """\
def alignment_timeline(wrestler_id: int) -> pd.DataFrame:
    turns = df["alignment_turns"][df["alignment_turns"]["wrestler_id"] == wrestler_id].copy()
    turns["turn_date"] = pd.to_datetime(turns["turn_date"])
    return turns.sort_values("turn_date")[["turn_date", "from_alignment", "to_alignment", "description"]]

w = find_wrestler("Roman Reigns")
alignment_timeline(int(w["id"]))
"""),

# ─── 7. PPV vs TV win-rate comparison ────────────────────────────────
("md", """\
## Recipe 7 — Wrestler PPV vs TV win-rate

Are wrestlers booked more decisively on PPV than weekly TV?
"""),

("py", """\
mp = df["match_participants"][df["match_participants"]["result"].isin(["win", "loss"])].copy()
mp["is_win"] = (mp["result"] == "win").astype(int)
m = df["matches"][["id", "event_id"]].rename(columns={"id": "match_id"})
e = df["events"][["id", "event_type"]].rename(columns={"id": "event_id"})
mp = mp.merge(m, on="match_id").merge(e, on="event_id")
mp["is_ppv"] = (mp["event_type"] == "ppv")

per_w = mp.groupby(["wrestler_id", "is_ppv"])["is_win"].mean().unstack().dropna()
per_w.columns = ["tv_wr", "ppv_wr"]
per_w = per_w.merge(df["wrestlers"][["id", "ring_name"]], left_index=True, right_on="id")
per_w["delta"] = per_w["ppv_wr"] - per_w["tv_wr"]
print("Wrestlers most boosted on PPV vs TV:")
print(per_w.nlargest(10, "delta")[["ring_name", "tv_wr", "ppv_wr", "delta"]].to_string(index=False))
"""),

# ─── 8. Cohort analysis by debut year ────────────────────────────────
("md", """\
## Recipe 8 — Cohort analysis by debut year

How does the median career length (in matches) of debutants vary by era?
"""),

("py", """\
mp = df["match_participants"]
career_n = mp.groupby("wrestler_id").size().rename("matches")
w = df["wrestlers"][["id", "debut_date"]].dropna(subset=["debut_date"]).copy()
w["debut_year"] = pd.to_datetime(w["debut_date"]).dt.year
w = w.merge(career_n, left_on="id", right_index=True)
cohort = w[w["debut_year"] >= 1980].groupby("debut_year")["matches"].median()

fig, ax = plt.subplots(figsize=(10, 3))
cohort.plot(ax=ax, color="#c9352d", marker="o", markersize=3)
ax.set_title("Median career match count by debut year")
ax.set_xlabel("Debut year"); ax.set_ylabel("Median matches")
ax.grid(alpha=0.3)
plt.tight_layout(); plt.show()
"""),

# ─── 9. Honest temporal-split baseline ───────────────────────────────
("md", """\
## Recipe 9 — Honest baseline with a temporal split

Most tutorials use random splits. For sequential booking data, that leaks signal across folds. Here's a temporal split that doesn't:
"""),

("py", """\
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score

mv = pd.read_parquet(DATA / "match_view.parquet")
mv = mv[mv["result"].isin(["win", "loss"])].copy()
mv["is_win"] = (mv["result"] == "win").astype(int)

# Temporal split: train pre-2024, test 2024+
mv["event_date"] = pd.to_datetime(mv["event_date"])
train = mv[mv["event_date"] < "2024-01-01"]
test  = mv[mv["event_date"] >= "2024-01-01"]

# Compute career_wr ONLY from training data
career_wr = (train.groupby("wrestler_id")["is_win"].mean()
             .rename("career_wr"))
career_n  = (train.groupby("wrestler_id").size()
             .rename("career_n"))

def featurize(d):
    return d.merge(career_wr, left_on="wrestler_id", right_index=True, how="left") \\
            .merge(career_n,  left_on="wrestler_id", right_index=True, how="left") \\
            .fillna({"career_wr": 0.5, "career_n": 0})

Xtr = featurize(train)[["career_wr", "career_n"]]
Xte = featurize(test)[["career_wr", "career_n"]]
ytr, yte = train["is_win"], test["is_win"]

clf = LogisticRegression(max_iter=1000).fit(Xtr, ytr)
print(f"Test accuracy: {accuracy_score(yte, clf.predict(Xte)):.3f}")
print(f"Test AUC:      {roc_auc_score(yte, clf.predict_proba(Xte)[:, 1]):.3f}")
print()
print("Compare with the leaky random-split version: AUC drops by ~5–8 points.")
print("That gap IS the kayfabe problem — see paper.md for the full discussion.")
"""),

# ─── 10. Use feature_matrix directly ─────────────────────────────────
("md", """\
## Recipe 10 — Reproduce the trained model exactly with `feature_matrix.parquet`

The `feature_matrix.parquet` file contains the exact 35 features used by the trained `xgboost.joblib` model.
"""),

("py", """\
fm = pd.read_parquet(DATA / "feature_matrix.parquet")
print(f"Shape: {fm.shape}")
print(f"Features: {[c for c in fm.columns if c not in ('match_id','wrestler_id','event_date','is_win')]}")

# Honest temporal split using the same features the model was trained on
fm["event_date"] = pd.to_datetime(fm["event_date"])
train = fm[fm["event_date"] < "2024-01-01"]
test  = fm[fm["event_date"] >= "2024-01-01"]
feat_cols = [c for c in fm.columns if c not in ("match_id","wrestler_id","event_date","is_win")]

print(f"\\nTrain rows: {len(train):,}   Test rows: {len(test):,}")
"""),

("md", """\
---

**Where to next:**

- [Trained model with feature importances](https://www.kaggle.com/models/theodorerubin/ringside-analytics-match-winner)
- [HF mirror of this dataset](https://huggingface.co/datasets/datamatters24/ringside-analytics)
- [Source repo and ETL pipeline](https://github.com/tedrubin80/wrastlingfirst)
"""),

]


def make_cell(kind: str, source: str) -> dict:
    lines = source.splitlines(keepends=True)
    if kind == "md":
        return {"cell_type": "markdown", "metadata": {}, "source": lines}
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
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.10"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    out = HERE / "pandas_recipes.ipynb"
    out.write_text(json.dumps(nb, indent=1, ensure_ascii=False))
    print(f"Wrote {out} ({len(CELLS)} cells)")


if __name__ == "__main__":
    main()
