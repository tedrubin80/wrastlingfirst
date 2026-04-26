"""Generate figures for the paper from the published parquets.

Usage:
    python3 build_figures.py
Output:
    docs/figures/*.png
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

DATA = Path("/var/www/wrastling/data/kaggle")
OUT = Path(__file__).parent / "figures"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams["figure.dpi"] = 110
plt.rcParams["savefig.dpi"] = 150
plt.rcParams["font.family"] = "DejaVu Sans"

RED = "#c9352d"

# ─── Figure 1: win-rate distribution (the kayfabe signature) ──────────
mp = pd.read_parquet(DATA / "match_participants.parquet")
mp["is_win"] = (mp["result"] == "win").astype(int)
career = mp.groupby("wrestler_id").agg(
    matches=("is_win", "size"),
    win_rate=("is_win", "mean"),
).query("matches >= 50")

fig, ax = plt.subplots(figsize=(9, 4))
ax.hist(career["win_rate"], bins=50, color=RED, alpha=0.85, edgecolor="white")
ax.axvline(0.5, color="black", linestyle="--", linewidth=1, label="coin flip (0.5)")
ax.set_title(f"Career win-rate distribution — {len(career):,} wrestlers (≥50 matches)")
ax.set_xlabel("Career win rate")
ax.set_ylabel("Wrestlers")
ax.legend()
plt.tight_layout()
plt.savefig(OUT / "win_rate_distribution.png", bbox_inches="tight")
plt.close()
print(f"wrote {OUT / 'win_rate_distribution.png'}")

# ─── Figure 2: matches per year (coverage) ─────────────────────────────
matches = pd.read_parquet(DATA / "matches.parquet")
events = pd.read_parquet(DATA / "events.parquet")[["id", "date"]].rename(columns={"id": "event_id"})
me = matches.merge(events, on="event_id")
me["year"] = pd.to_datetime(me["date"]).dt.year
per_year = me.groupby("year").size()
per_year = per_year[per_year.index >= 1980]

fig, ax = plt.subplots(figsize=(11, 4))
per_year.plot(ax=ax, color=RED, linewidth=2)
ax.fill_between(per_year.index, 0, per_year.values, color=RED, alpha=0.15)
ax.set_title("Matches per year — Ringside Wrestling Archive")
ax.set_xlabel("Year")
ax.set_ylabel("Matches")
ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(OUT / "matches_per_year.png", bbox_inches="tight")
plt.close()
print(f"wrote {OUT / 'matches_per_year.png'}")

# ─── Figure 3: promotion share ─────────────────────────────────────────
promotions = pd.read_parquet(DATA / "promotions.parquet")[["id", "abbreviation"]].rename(columns={"id": "promotion_id"})
em = (matches
      .merge(events.rename(columns={"event_id": "event_id"}), on="event_id")
      .merge(pd.read_parquet(DATA / "events.parquet")[["id", "promotion_id"]].rename(columns={"id": "event_id"}), on="event_id")
      .merge(promotions, on="promotion_id"))
share = em["abbreviation"].value_counts()

fig, ax = plt.subplots(figsize=(8, 4))
share.plot.barh(ax=ax, color=RED)
ax.set_title("Matches by promotion")
ax.set_xlabel("Matches")
ax.invert_yaxis()
plt.tight_layout()
plt.savefig(OUT / "promotion_share.png", bbox_inches="tight")
plt.close()
print(f"wrote {OUT / 'promotion_share.png'}")

# ─── Figure 4: title reign length distribution ─────────────────────────
tr = pd.read_parquet(DATA / "title_reigns.parquet").copy()
tr["won_date"] = pd.to_datetime(tr["won_date"])
tr["lost_date"] = pd.to_datetime(tr["lost_date"])
today = pd.Timestamp.today().normalize()
tr["length_days"] = (tr["lost_date"].fillna(today) - tr["won_date"]).dt.days
tr = tr[tr["length_days"] > 0]

fig, ax = plt.subplots(figsize=(10, 4))
ax.hist(tr["length_days"].clip(upper=730), bins=60, color=RED, alpha=0.85, edgecolor="white")
ax.set_title("Title reign length (days, capped at 2 years for visibility)")
ax.set_xlabel("Days held")
ax.set_ylabel("Reigns")
plt.tight_layout()
plt.savefig(OUT / "title_reign_lengths.png", bbox_inches="tight")
plt.close()
print(f"wrote {OUT / 'title_reign_lengths.png'}")

print(f"\nAll figures in {OUT}")
