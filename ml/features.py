"""
Feature engineering pipeline for match outcome prediction.

Computes per-wrestler, per-match features from historical booking patterns.
The model learns what bookers tend to do — not who is the "better" wrestler.
"""

import os
from datetime import date, timedelta

import numpy as np
import pandas as pd
import psycopg2
import structlog

logger = structlog.get_logger(__name__)

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://ringside:ringside@localhost:5432/ringside",
)


def get_connection() -> psycopg2.extensions.connection:
    return psycopg2.connect(DB_URL)


def load_match_data(conn: psycopg2.extensions.connection) -> pd.DataFrame:
    """Load all match participation records with event context."""
    query = """
    SELECT
        mp.match_id,
        mp.wrestler_id,
        mp.result,
        mp.team_number,
        m.match_type,
        m.match_order,
        m.title_match,
        m.rating,
        m.duration_seconds,
        e.date AS event_date,
        e.event_type,
        e.promotion_id,
        p.abbreviation AS promotion,
        (SELECT count(*) FROM matches m2 WHERE m2.event_id = e.id) AS card_size
    FROM match_participants mp
    JOIN matches m ON m.id = mp.match_id
    JOIN events e ON e.id = m.event_id
    LEFT JOIN promotions p ON p.id = e.promotion_id
    WHERE mp.result IN ('win', 'loss')
      AND e.date IS NOT NULL
    ORDER BY e.date ASC, m.match_order ASC
    """
    return pd.read_sql(query, conn)


def load_title_data(conn: psycopg2.extensions.connection) -> pd.DataFrame:
    """Load title reign data for title proximity features."""
    query = """
    SELECT wrestler_id, title_id, won_date, lost_date, defenses
    FROM title_reigns
    ORDER BY won_date
    """
    return pd.read_sql(query, conn)


def load_alignment_data(conn: psycopg2.extensions.connection) -> pd.DataFrame:
    """Load alignment snapshots and turns for alignment features."""
    query = """
    SELECT wrestler_id, alignment, effective_date
    FROM wrestler_alignments
    ORDER BY wrestler_id, effective_date
    """
    return pd.read_sql(query, conn)


def load_alignment_turns(conn: psycopg2.extensions.connection) -> pd.DataFrame:
    """Load alignment turn events."""
    query = """
    SELECT wrestler_id, from_alignment, to_alignment, turn_date
    FROM alignment_turns
    ORDER BY wrestler_id, turn_date
    """
    return pd.read_sql(query, conn)


def compute_rolling_win_rate(
    group: pd.DataFrame, window_days: int, date_col: str = "event_date"
) -> pd.Series:
    """Compute rolling win rate over a time window for each row."""
    results = []
    dates = group[date_col].values
    wins = (group["result"] == "win").values

    for i in range(len(group)):
        cutoff = dates[i] - np.timedelta64(window_days, "D")
        mask = (dates[:i] >= cutoff) & (dates[:i] < dates[i])
        total = mask.sum()
        if total == 0:
            results.append(0.5)  # No history — assume neutral
        else:
            results.append(wins[:i][mask].sum() / total)

    return pd.Series(results, index=group.index)


def compute_streak(group: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Compute current win streak and loss streak at each point in time."""
    win_streaks = []
    loss_streaks = []
    current_win = 0
    current_loss = 0

    for result in group["result"]:
        if result == "win":
            current_win += 1
            current_loss = 0
        else:
            current_loss += 1
            current_win = 0
        win_streaks.append(current_win)
        loss_streaks.append(current_loss)

    return (
        pd.Series(win_streaks, index=group.index),
        pd.Series(loss_streaks, index=group.index),
    )


def compute_match_type_win_rate(df: pd.DataFrame) -> pd.Series:
    """Historical win rate for this wrestler in this specific match type."""
    results = pd.Series(0.5, index=df.index)

    for wrestler_id in df["wrestler_id"].unique():
        mask = df["wrestler_id"] == wrestler_id
        wrestler_df = df[mask].copy()

        for match_type in wrestler_df["match_type"].unique():
            type_mask = wrestler_df["match_type"] == match_type
            type_df = wrestler_df[type_mask]

            running_wins = (type_df["result"] == "win").cumsum().shift(1, fill_value=0)
            running_total = pd.Series(range(len(type_df)), index=type_df.index)

            rate = running_wins / running_total.replace(0, np.nan)
            rate = rate.fillna(0.5)

            results.loc[type_df.index] = rate

    return results


def build_features(
    df: pd.DataFrame,
    title_df: pd.DataFrame,
    alignment_df: pd.DataFrame | None = None,
    turns_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build the full feature matrix from raw match data."""
    logger.info("building_features", total_records=len(df))

    df = df.sort_values(["wrestler_id", "event_date"]).copy()
    df["event_date"] = pd.to_datetime(df["event_date"])
    df["won"] = (df["result"] == "win").astype(int)

    features = pd.DataFrame(index=df.index)
    features["match_id"] = df["match_id"]
    features["wrestler_id"] = df["wrestler_id"]
    features["event_date"] = df["event_date"]
    features["won"] = df["won"]

    # === Win Momentum ===
    logger.info("computing_win_momentum")
    for wrestler_id, group in df.groupby("wrestler_id"):
        idx = group.index
        features.loc[idx, "win_rate_30d"] = compute_rolling_win_rate(group, 30)
        features.loc[idx, "win_rate_90d"] = compute_rolling_win_rate(group, 90)
        features.loc[idx, "win_rate_365d"] = compute_rolling_win_rate(group, 365)

        win_streak, loss_streak = compute_streak(group)
        # Shift by 1 so we use the streak BEFORE this match
        features.loc[idx, "current_win_streak"] = win_streak.shift(1, fill_value=0)
        features.loc[idx, "current_loss_streak"] = loss_streak.shift(1, fill_value=0)

    # === Event Context ===
    logger.info("computing_event_context")
    features["is_ppv"] = (df["event_type"] == "ppv").astype(int)
    features["is_title_match"] = df["title_match"].astype(int)

    # Card position (normalized 0-1, where 1 = main event)
    features["card_position"] = df.apply(
        lambda row: row["match_order"] / row["card_size"]
        if row["card_size"] > 0
        else 0.5,
        axis=1,
    )

    # Event significance tier
    tier_map = {"ppv": 3, "special": 2, "weekly_tv": 1, "house_show": 0, "tournament": 2}
    features["event_tier"] = df["event_type"].map(tier_map).fillna(1).astype(int)

    # === Match Type ===
    logger.info("computing_match_type_features")
    features["match_type_win_rate"] = compute_match_type_win_rate(df)

    # One-hot encode common match types
    common_types = ["singles", "tag_team", "triple_threat", "fatal_four_way",
                    "ladder", "cage", "hell_in_a_cell", "royal_rumble"]
    for mt in common_types:
        features[f"is_{mt}"] = (df["match_type"] == mt).astype(int)

    # === Title Proximity ===
    logger.info("computing_title_proximity")
    if len(title_df) > 0:
        title_df["won_date"] = pd.to_datetime(title_df["won_date"])
        title_df["lost_date"] = pd.to_datetime(title_df["lost_date"])

        for wrestler_id, group in df.groupby("wrestler_id"):
            idx = group.index
            w_titles = title_df[title_df["wrestler_id"] == wrestler_id]

            for i, (row_idx, row) in enumerate(group.iterrows()):
                match_date = row["event_date"]

                # Is champion at time of match?
                active_reigns = w_titles[
                    (w_titles["won_date"] <= match_date)
                    & ((w_titles["lost_date"].isna()) | (w_titles["lost_date"] >= match_date))
                ]
                features.loc[row_idx, "is_champion"] = int(len(active_reigns) > 0)
                features.loc[row_idx, "num_defenses"] = (
                    active_reigns["defenses"].sum() if len(active_reigns) > 0 else 0
                )

                # Days since last title match
                past_title_matches = group.loc[:row_idx]
                past_title = past_title_matches[past_title_matches["title_match"] == True]
                if len(past_title) > 0:
                    last_title_date = pd.to_datetime(past_title.iloc[-1]["event_date"])
                    features.loc[row_idx, "days_since_title_match"] = (
                        match_date - last_title_date
                    ).days
                else:
                    features.loc[row_idx, "days_since_title_match"] = 999
    else:
        features["is_champion"] = 0
        features["num_defenses"] = 0
        features["days_since_title_match"] = 999

    # === Career Phase ===
    logger.info("computing_career_phase")
    for wrestler_id, group in df.groupby("wrestler_id"):
        idx = group.index
        first_match = group["event_date"].min()
        features.loc[idx, "years_active"] = (
            (group["event_date"] - first_match).dt.days / 365.25
        )

        # Activity level: matches in last 90 days
        dates = group["event_date"].values
        for i, row_idx in enumerate(idx):
            cutoff = dates[i] - np.timedelta64(90, "D")
            features.loc[row_idx, "matches_last_90d"] = (
                (dates[:i] >= cutoff) & (dates[:i] < dates[i])
            ).sum()

        # Days since last match
        features.loc[idx, "days_since_last_match"] = (
            group["event_date"].diff().dt.days.fillna(30)
        )

    # === Promotion Context ===
    logger.info("computing_promotion_context")
    # Promotion-specific win rate (rolling)
    for (wrestler_id, promotion), group in df.groupby(["wrestler_id", "promotion"]):
        idx = group.index
        features.loc[idx, "promotion_win_rate"] = compute_rolling_win_rate(group, 365)

    features["promotion_win_rate"] = features["promotion_win_rate"].fillna(0.5)

    # === Alignment Features ===
    logger.info("computing_alignment_features")
    if alignment_df is not None and len(alignment_df) > 0:
        alignment_df = alignment_df.copy()
        alignment_df["effective_date"] = pd.to_datetime(alignment_df["effective_date"])
        alignment_map = {"face": 0, "tweener": 1, "heel": 2}

        for wrestler_id, group in df.groupby("wrestler_id"):
            idx = group.index
            w_align = alignment_df[alignment_df["wrestler_id"] == wrestler_id].sort_values("effective_date")

            if len(w_align) == 0:
                features.loc[idx, "alignment"] = 1  # unknown → tweener
                features.loc[idx, "is_face"] = 0
                features.loc[idx, "is_heel"] = 0
                continue

            # For each match, find most recent alignment
            for row_idx, row in group.iterrows():
                match_date = row["event_date"]
                prior = w_align[w_align["effective_date"] <= match_date]
                if len(prior) > 0:
                    current = prior.iloc[-1]["alignment"]
                    features.loc[row_idx, "alignment"] = alignment_map.get(current, 1)
                    features.loc[row_idx, "is_face"] = int(current == "face")
                    features.loc[row_idx, "is_heel"] = int(current == "heel")
                else:
                    features.loc[row_idx, "alignment"] = 1
                    features.loc[row_idx, "is_face"] = 0
                    features.loc[row_idx, "is_heel"] = 0
    else:
        features["alignment"] = 1
        features["is_face"] = 0
        features["is_heel"] = 0

    # Turn recency and frequency
    if turns_df is not None and len(turns_df) > 0:
        turns_df = turns_df.copy()
        turns_df["turn_date"] = pd.to_datetime(turns_df["turn_date"])

        for wrestler_id, group in df.groupby("wrestler_id"):
            idx = group.index
            w_turns = turns_df[turns_df["wrestler_id"] == wrestler_id].sort_values("turn_date")

            for row_idx, row in group.iterrows():
                match_date = row["event_date"]
                prior_turns = w_turns[w_turns["turn_date"] < match_date]

                if len(prior_turns) > 0:
                    last_turn = prior_turns.iloc[-1]["turn_date"]
                    features.loc[row_idx, "days_since_turn"] = (match_date - last_turn).days
                else:
                    features.loc[row_idx, "days_since_turn"] = 999

                # Turns in last 12 months
                cutoff = match_date - pd.Timedelta(days=365)
                features.loc[row_idx, "turns_12m"] = len(
                    prior_turns[prior_turns["turn_date"] >= cutoff]
                )
    else:
        features["days_since_turn"] = 999
        features["turns_12m"] = 0

    # === Match Rating History ===
    logger.info("computing_rating_features")
    # Average match rating as a proxy for push/booking quality
    for wrestler_id, group in df.groupby("wrestler_id"):
        idx = group.index
        ratings = group["rating"].values
        running_sum = 0.0
        running_count = 0
        avg_ratings = []

        for i in range(len(group)):
            # Use pre-match average (shifted by 1)
            if running_count > 0:
                avg_ratings.append(running_sum / running_count)
            else:
                avg_ratings.append(0.0)

            if pd.notna(ratings[i]) and ratings[i] > 0:
                running_sum += ratings[i]
                running_count += 1

        features.loc[idx, "avg_match_rating"] = avg_ratings

    features["avg_match_rating"] = features["avg_match_rating"].fillna(0)

    # === Card Position Momentum ===
    logger.info("computing_card_position_momentum")
    # Rolling average card position (last 10 matches) — vectorized per wrestler
    features["card_position_momentum"] = (
        features.groupby(df["wrestler_id"])["card_position"]
        .transform(lambda s: s.shift(1).rolling(10, min_periods=1).mean())
        .fillna(0.5)
    )

    # === Head-to-Head ===
    logger.info("computing_head_to_head")
    # Pre-build a dict of (pair) -> list of (date, w1_won) for O(1) lookups
    # Only for 2-person matches
    singles_matches = df.groupby("match_id").filter(lambda g: len(g) == 2)
    singles_sorted = singles_matches.sort_values("event_date")

    # Build pair history incrementally
    from collections import defaultdict
    pair_history = defaultdict(lambda: {"wins": defaultdict(int), "total": 0})

    h2h_win_rate = pd.Series(0.5, index=df.index)
    h2h_matches_col = pd.Series(0, index=df.index, dtype=int)

    for match_id, match_group in singles_sorted.groupby("match_id", sort=False):
        rows = match_group.index.tolist()
        if len(rows) != 2:
            continue

        w1_id = match_group.loc[rows[0], "wrestler_id"]
        w2_id = match_group.loc[rows[1], "wrestler_id"]
        w1_result = match_group.loc[rows[0], "result"]

        pair_key = (min(w1_id, w2_id), max(w1_id, w2_id))
        hist = pair_history[pair_key]

        if hist["total"] > 0:
            w1_wins = hist["wins"][w1_id]
            w1_rate = w1_wins / hist["total"]
            h2h_win_rate.loc[rows[0]] = w1_rate
            h2h_win_rate.loc[rows[1]] = 1 - w1_rate
            h2h_matches_col.loc[rows[0]] = hist["total"]
            h2h_matches_col.loc[rows[1]] = hist["total"]

        # Update history AFTER computing features (no future leakage)
        if w1_result == "win":
            hist["wins"][w1_id] += 1
        else:
            hist["wins"][w2_id] += 1
        hist["total"] += 1

    features["h2h_win_rate"] = h2h_win_rate
    features["h2h_matches"] = h2h_matches_col

    # === Face vs Heel Matchup ===
    logger.info("computing_face_heel_matchup")
    # Vectorized: join each wrestler's alignment with their opponent's
    features["face_heel_matchup"] = 0
    if "alignment" in features.columns:
        for match_id, match_group in singles_sorted.groupby("match_id", sort=False):
            rows = match_group.index.tolist()
            if len(rows) != 2:
                continue
            a1 = features.loc[rows[0], "alignment"]
            a2 = features.loc[rows[1], "alignment"]
            is_fh = int((a1 == 0 and a2 == 2) or (a1 == 2 and a2 == 0))
            features.loc[rows[0], "face_heel_matchup"] = is_fh
            features.loc[rows[1], "face_heel_matchup"] = is_fh

    # Fill remaining NaN
    features = features.fillna(0)

    logger.info(
        "features_built",
        shape=features.shape,
        columns=list(features.columns),
    )

    return features


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
    # Alignment (6) — NEW
    "alignment", "is_face", "is_heel",
    "days_since_turn", "turns_12m", "face_heel_matchup",
    # Match quality (1) — NEW
    "avg_match_rating",
    # Card position momentum (1) — NEW
    "card_position_momentum",
]


def build_feature_matrix(
    conn: psycopg2.extensions.connection | None = None,
) -> pd.DataFrame:
    """Full pipeline: load data, compute features, return matrix."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    try:
        logger.info("loading_match_data")
        match_df = load_match_data(conn)
        logger.info("match_data_loaded", records=len(match_df))

        logger.info("loading_title_data")
        title_df = load_title_data(conn)
        logger.info("title_data_loaded", records=len(title_df))

        logger.info("loading_alignment_data")
        alignment_df = load_alignment_data(conn)
        logger.info("alignment_data_loaded", records=len(alignment_df))

        logger.info("loading_alignment_turns")
        turns_df = load_alignment_turns(conn)
        logger.info("turns_data_loaded", records=len(turns_df))

        features = build_features(match_df, title_df, alignment_df, turns_df)
        return features

    finally:
        if own_conn:
            conn.close()


if __name__ == "__main__":
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )

    features = build_feature_matrix()
    print(f"\nFeature matrix: {features.shape}")
    print(f"Columns: {list(features.columns)}")
    print(f"\nTarget distribution:\n{features['won'].value_counts()}")
    print(f"\nSample features:\n{features[FEATURE_COLUMNS].describe()}")

    # Save for inspection
    features.to_parquet("ml/features.parquet", index=False)
    print("\nSaved to ml/features.parquet")
