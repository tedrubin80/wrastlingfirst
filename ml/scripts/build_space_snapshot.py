"""Build the wrestler stats snapshot bundled with the HF Space.

For each of the top N wrestlers by match count, computes their **current
pre-match state** for all wrestler-specific features the trained model needs.
Also builds a sparse head-to-head table.

Bundling these snapshots with the Space means inference runs without any DB
dependency. Users just pick two wrestlers from a dropdown and get a prediction.

Outputs (overwrites):
    spaces/ringside_predictor/data/wrestler_stats.parquet
    spaces/ringside_predictor/data/h2h.parquet
    spaces/ringside_predictor/data/match_type_stats.parquet
    spaces/ringside_predictor/data/snapshot_manifest.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import psycopg2

DB_URL = "postgresql://ringside:ringside@localhost:5432/ringside"
REPO_ROOT = Path("/var/www/wrastling")
OUT_DIR = REPO_ROOT / "spaces" / "ringside_predictor" / "data"
TOP_N = 500   # top-N wrestlers by match count

OUT_DIR.mkdir(parents=True, exist_ok=True)


def main() -> int:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    print(f"Building snapshot for top {TOP_N} wrestlers...")

    # ─── 1. Top-N wrestlers ──────────────────────────────────────────
    cur.execute("""
        SELECT mp.wrestler_id, COUNT(*) AS n
        FROM match_participants mp
        GROUP BY mp.wrestler_id
        ORDER BY n DESC
        LIMIT %s
    """, (TOP_N,))
    top_ids = [row[0] for row in cur.fetchall()]
    print(f"  selected {len(top_ids)} wrestlers")

    placeholders = ",".join(["%s"] * len(top_ids))

    # ─── 2. Per-wrestler current state ───────────────────────────────
    print("  computing per-wrestler stats...")
    stats_query = f"""
    WITH last_event AS (
        SELECT MAX(e.date) AS today
        FROM matches m JOIN events e ON e.id = m.event_id
    ),
    wrestler_matches AS (
        SELECT
            mp.wrestler_id,
            m.id AS match_id,
            e.date AS event_date,
            mp.result,
            (mp.result = 'win')::int AS won,
            ROW_NUMBER() OVER (PARTITION BY mp.wrestler_id ORDER BY e.date DESC) AS rn_desc
        FROM match_participants mp
        JOIN matches m ON m.id = mp.match_id
        JOIN events e ON e.id = m.event_id
        WHERE mp.wrestler_id IN ({placeholders})
          AND mp.result IN ('win', 'loss')
    ),
    streaks AS (
        SELECT
            wrestler_id,
            (SELECT result FROM wrestler_matches wm2 WHERE wm2.wrestler_id = wm.wrestler_id ORDER BY event_date DESC LIMIT 1) AS last_result
        FROM wrestler_matches wm
        GROUP BY wrestler_id
    )
    SELECT
        w.id AS wrestler_id,
        w.ring_name,
        w.gender,
        w.debut_date,
        w.primary_promotion_id,
        COALESCE(p.abbreviation, 'OTHER') AS primary_promotion_abbr,
        -- Career
        COUNT(wm.match_id)                                AS career_matches,
        AVG(wm.won)::float                                AS career_wr,
        -- Recent windows
        AVG(wm.won) FILTER (
            WHERE wm.event_date >= (SELECT today FROM last_event) - INTERVAL '30 days'
        )::float AS win_rate_30d,
        AVG(wm.won) FILTER (
            WHERE wm.event_date >= (SELECT today FROM last_event) - INTERVAL '90 days'
        )::float AS win_rate_90d,
        AVG(wm.won) FILTER (
            WHERE wm.event_date >= (SELECT today FROM last_event) - INTERVAL '365 days'
        )::float AS win_rate_365d,
        COUNT(*) FILTER (
            WHERE wm.event_date >= (SELECT today FROM last_event) - INTERVAL '90 days'
        )::int AS matches_last_90d,
        -- Days since last match
        ((SELECT today FROM last_event) - MAX(wm.event_date))::int AS days_since_last_match,
        -- Years active (debut → most recent match) — date diff is days
        ((MAX(wm.event_date) - MIN(wm.event_date)) / 365.25)::float AS years_active
    FROM wrestlers w
    LEFT JOIN promotions p ON p.id = w.primary_promotion_id
    LEFT JOIN wrestler_matches wm ON wm.wrestler_id = w.id
    WHERE w.id IN ({placeholders})
    GROUP BY w.id, w.ring_name, w.gender, w.debut_date, w.primary_promotion_id, p.abbreviation
    """
    df = pd.read_sql_query(stats_query, conn, params=top_ids + top_ids)

    # ─── 3. Compute streak features explicitly ──────────────────────
    # Get last 20 results per wrestler and count consecutive wins/losses
    streak_query = f"""
    SELECT
        mp.wrestler_id,
        e.date AS event_date,
        mp.result
    FROM match_participants mp
    JOIN matches m ON m.id = mp.match_id
    JOIN events e ON e.id = m.event_id
    WHERE mp.wrestler_id IN ({placeholders})
      AND mp.result IN ('win', 'loss')
    ORDER BY mp.wrestler_id, e.date DESC
    """
    rs = pd.read_sql_query(streak_query, conn, params=top_ids)

    def compute_streaks(group):
        if group.empty:
            return pd.Series({"current_win_streak": 0, "current_loss_streak": 0})
        # Last result first (already DESC sorted)
        results = group["result"].tolist()
        last = results[0]
        streak = 0
        for r in results:
            if r != last:
                break
            streak += 1
        if last == "win":
            return pd.Series({"current_win_streak": streak, "current_loss_streak": 0})
        else:
            return pd.Series({"current_win_streak": 0, "current_loss_streak": streak})

    streaks_df = rs.groupby("wrestler_id").apply(compute_streaks).reset_index()
    df = df.merge(streaks_df, on="wrestler_id", how="left")
    df["current_win_streak"]  = df["current_win_streak"].fillna(0).astype(int)
    df["current_loss_streak"] = df["current_loss_streak"].fillna(0).astype(int)

    # ─── 4. Title status ────────────────────────────────────────────
    title_query = f"""
    SELECT
        wrestler_id,
        BOOL_OR(lost_date IS NULL)        AS is_champion,
        MAX(defenses)                      AS num_defenses,
        ((SELECT MAX(date) FROM events) - MAX(won_date))::int AS days_since_title_match
    FROM title_reigns
    WHERE wrestler_id IN ({placeholders})
    GROUP BY wrestler_id
    """
    titles = pd.read_sql_query(title_query, conn, params=top_ids)
    df = df.merge(titles, on="wrestler_id", how="left")
    df["is_champion"]            = df["is_champion"].fillna(False).astype(bool)
    df["num_defenses"]           = df["num_defenses"].fillna(0).astype(int)
    df["days_since_title_match"] = df["days_since_title_match"].fillna(9999).astype(int)

    # ─── 5. Alignment ───────────────────────────────────────────────
    align_query = f"""
    SELECT DISTINCT ON (wrestler_id)
        wrestler_id,
        to_alignment AS alignment,
        ((SELECT MAX(date) FROM events) - turn_date)::int AS days_since_turn
    FROM alignment_turns
    WHERE wrestler_id IN ({placeholders})
    ORDER BY wrestler_id, turn_date DESC
    """
    align = pd.read_sql_query(align_query, conn, params=top_ids)
    df = df.merge(align, on="wrestler_id", how="left")
    df["alignment"]       = df["alignment"].fillna("face")
    df["is_face"]         = (df["alignment"] == "face").astype(int)
    df["is_heel"]         = (df["alignment"] == "heel").astype(int)
    df["days_since_turn"] = df["days_since_turn"].fillna(9999).astype(int)

    align_count_q = f"""
    SELECT
        wrestler_id,
        COUNT(*) FILTER (
            WHERE turn_date >= (SELECT MAX(date) FROM events) - INTERVAL '12 months'
        )::int AS turns_12m
    FROM alignment_turns
    WHERE wrestler_id IN ({placeholders})
    GROUP BY wrestler_id
    """
    turns = pd.read_sql_query(align_count_q, conn, params=top_ids)
    df = df.merge(turns, on="wrestler_id", how="left")
    df["turns_12m"] = df["turns_12m"].fillna(0).astype(int)

    # ─── 6. Average match rating per wrestler ──────────────────────
    rating_q = f"""
    SELECT
        mp.wrestler_id,
        AVG(m.rating)::float AS avg_match_rating
    FROM match_participants mp
    JOIN matches m ON m.id = mp.match_id
    WHERE mp.wrestler_id IN ({placeholders})
      AND m.rating IS NOT NULL
    GROUP BY mp.wrestler_id
    """
    ratings = pd.read_sql_query(rating_q, conn, params=top_ids)
    df = df.merge(ratings, on="wrestler_id", how="left")
    df["avg_match_rating"] = df["avg_match_rating"].fillna(5.0)

    # ─── 7. Promotion win rate ─────────────────────────────────────
    promo_q = f"""
    SELECT
        e.promotion_id,
        AVG((mp.result = 'win')::int)::float AS promotion_win_rate
    FROM match_participants mp
    JOIN matches m ON m.id = mp.match_id
    JOIN events e ON e.id = m.event_id
    WHERE mp.result IN ('win', 'loss')
    GROUP BY e.promotion_id
    """
    promo_wr = pd.read_sql_query(promo_q, conn)
    df = df.merge(
        promo_wr,
        left_on="primary_promotion_id",
        right_on="promotion_id",
        how="left",
        suffixes=("", "_promo"),
    )
    df = df.drop(columns=[c for c in ("promotion_id",) if c in df.columns])
    if "promotion_win_rate" not in df.columns:
        df["promotion_win_rate"] = 0.5
    df["promotion_win_rate"] = df["promotion_win_rate"].fillna(0.5)

    # ─── 8. Card position momentum (rough proxy) ─────────────────────
    # Approximate as average match_order in last 20 matches — lower = more main-event
    card_q = f"""
    WITH recent AS (
        SELECT mp.wrestler_id, m.match_order, e.date,
               ROW_NUMBER() OVER (PARTITION BY mp.wrestler_id ORDER BY e.date DESC) AS rn
        FROM match_participants mp
        JOIN matches m ON m.id = mp.match_id
        JOIN events e ON e.id = m.event_id
        WHERE mp.wrestler_id IN ({placeholders})
          AND m.match_order IS NOT NULL
    )
    SELECT wrestler_id, AVG(match_order)::float AS avg_recent_card_position
    FROM recent
    WHERE rn <= 20
    GROUP BY wrestler_id
    """
    cards = pd.read_sql_query(card_q, conn, params=top_ids)
    df = df.merge(cards, on="wrestler_id", how="left")
    df["card_position_momentum"] = (-df["avg_recent_card_position"]).fillna(0.0)
    # higher = more main-event-y

    # ─── 9. Drop helper cols, finalize ─────────────────────────────
    df["years_active"] = df["years_active"].fillna(1.0)
    df["win_rate_30d"]  = df["win_rate_30d"].fillna(df["career_wr"])
    df["win_rate_90d"]  = df["win_rate_90d"].fillna(df["career_wr"])
    df["win_rate_365d"] = df["win_rate_365d"].fillna(df["career_wr"])
    df["matches_last_90d"] = df["matches_last_90d"].fillna(0).astype(int)
    df["days_since_last_match"] = df["days_since_last_match"].fillna(9999).astype(int)

    # Save
    out_path = OUT_DIR / "wrestler_stats.parquet"
    df.to_parquet(out_path, index=False)
    print(f"  wrote {out_path} ({len(df)} rows, {df.shape[1]} cols)")

    # ─── 10. Head-to-head among top wrestlers ────────────────────────
    print("  building h2h table...")
    h2h_q = f"""
    WITH singles AS (
        SELECT match_id
        FROM match_participants
        GROUP BY match_id
        HAVING COUNT(*) = 2
    ),
    pairs AS (
        SELECT
            s.match_id,
            LEAST(mp1.wrestler_id, mp2.wrestler_id) AS w_a,
            GREATEST(mp1.wrestler_id, mp2.wrestler_id) AS w_b,
            CASE
                WHEN mp1.wrestler_id < mp2.wrestler_id AND mp1.result = 'win' THEN 1
                WHEN mp1.wrestler_id > mp2.wrestler_id AND mp2.result = 'win' THEN 1
                ELSE 0
            END AS a_won
        FROM singles s
        JOIN match_participants mp1 ON mp1.match_id = s.match_id
        JOIN match_participants mp2 ON mp2.match_id = s.match_id AND mp1.id < mp2.id
    )
    SELECT w_a, w_b, COUNT(*) AS h2h_matches, AVG(a_won)::float AS a_win_rate
    FROM pairs
    WHERE w_a IN ({placeholders}) AND w_b IN ({placeholders})
    GROUP BY w_a, w_b
    HAVING COUNT(*) >= 2
    """
    h2h = pd.read_sql_query(h2h_q, conn, params=top_ids + top_ids)
    h2h_path = OUT_DIR / "h2h.parquet"
    h2h.to_parquet(h2h_path, index=False)
    print(f"  wrote {h2h_path} ({len(h2h)} pair rows)")

    # ─── 11. Per-(wrestler, match_type) win rate ─────────────────────
    print("  building match-type win-rate table...")
    mt_q = f"""
    SELECT
        mp.wrestler_id,
        m.match_type,
        AVG((mp.result = 'win')::int)::float AS win_rate,
        COUNT(*)::int AS n
    FROM match_participants mp
    JOIN matches m ON m.id = mp.match_id
    WHERE mp.wrestler_id IN ({placeholders})
      AND mp.result IN ('win', 'loss')
      AND m.match_type IS NOT NULL
    GROUP BY mp.wrestler_id, m.match_type
    """
    mt = pd.read_sql_query(mt_q, conn, params=top_ids)
    mt_path = OUT_DIR / "match_type_stats.parquet"
    mt.to_parquet(mt_path, index=False)
    print(f"  wrote {mt_path} ({len(mt)} rows)")

    # ─── 12. Manifest ───────────────────────────────────────────────
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "top_n_wrestlers": len(df),
        "h2h_pairs": len(h2h),
        "match_type_rows": len(mt),
        "feature_columns": [
            "win_rate_30d", "win_rate_90d", "win_rate_365d",
            "current_win_streak", "current_loss_streak",
            "is_ppv", "is_title_match", "card_position", "event_tier",
            "match_type_win_rate", "is_singles", "is_tag_team",
            "is_triple_threat", "is_fatal_four_way", "is_ladder",
            "is_cage", "is_hell_in_a_cell", "is_royal_rumble",
            "is_champion", "num_defenses", "days_since_title_match",
            "years_active", "matches_last_90d", "days_since_last_match",
            "promotion_win_rate", "h2h_win_rate", "h2h_matches",
            "alignment", "is_face", "is_heel",
            "days_since_turn", "turns_12m", "face_heel_matchup",
            "avg_match_rating", "card_position_momentum",
        ],
    }
    (OUT_DIR / "snapshot_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    print(f"\nSnapshot ready in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
