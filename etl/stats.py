"""Compute wrestler_stats_rolling after new data is loaded."""

import psycopg2.extensions
import structlog

logger = structlog.get_logger(__name__)


def recompute_rolling_stats(
    conn: psycopg2.extensions.connection,
    wrestler_ids: list[int] | None = None,
) -> int:
    """
    Recompute rolling stats for wrestlers affected by new match data.
    If wrestler_ids is None, recomputes for all wrestlers.
    Returns number of stat rows upserted.
    """
    where_clause = ""
    params: tuple = ()
    if wrestler_ids:
        where_clause = "WHERE w.id = ANY(%s)"
        params = (wrestler_ids,)

    query = f"""
    INSERT INTO wrestler_stats_rolling (
        wrestler_id, as_of_date,
        win_rate_30d, win_rate_90d, win_rate_365d,
        current_win_streak, current_loss_streak,
        momentum_score, push_score,
        matches_count_30d, matches_count_90d, matches_count_365d,
        title_match_rate, ppv_win_rate, avg_match_rating
    )
    SELECT
        w.id AS wrestler_id,
        CURRENT_DATE AS as_of_date,

        -- Win rates by time window
        COALESCE(
            SUM(CASE WHEN mp.result = 'win' AND e.date >= CURRENT_DATE - 30
                     THEN 1 ELSE 0 END)::DECIMAL /
            NULLIF(SUM(CASE WHEN e.date >= CURRENT_DATE - 30
                            THEN 1 ELSE 0 END), 0),
            0
        ) AS win_rate_30d,

        COALESCE(
            SUM(CASE WHEN mp.result = 'win' AND e.date >= CURRENT_DATE - 90
                     THEN 1 ELSE 0 END)::DECIMAL /
            NULLIF(SUM(CASE WHEN e.date >= CURRENT_DATE - 90
                            THEN 1 ELSE 0 END), 0),
            0
        ) AS win_rate_90d,

        COALESCE(
            SUM(CASE WHEN mp.result = 'win' AND e.date >= CURRENT_DATE - 365
                     THEN 1 ELSE 0 END)::DECIMAL /
            NULLIF(SUM(CASE WHEN e.date >= CURRENT_DATE - 365
                            THEN 1 ELSE 0 END), 0),
            0
        ) AS win_rate_365d,

        -- Streaks (simplified — computed from most recent matches)
        0 AS current_win_streak,
        0 AS current_loss_streak,

        -- Momentum: weighted recent win rate (30d * 0.5 + 90d * 0.3 + 365d * 0.2)
        COALESCE(
            0.5 * (SUM(CASE WHEN mp.result = 'win' AND e.date >= CURRENT_DATE - 30
                            THEN 1 ELSE 0 END)::DECIMAL /
                   NULLIF(SUM(CASE WHEN e.date >= CURRENT_DATE - 30
                                   THEN 1 ELSE 0 END), 0))
            + 0.3 * (SUM(CASE WHEN mp.result = 'win' AND e.date >= CURRENT_DATE - 90
                              THEN 1 ELSE 0 END)::DECIMAL /
                     NULLIF(SUM(CASE WHEN e.date >= CURRENT_DATE - 90
                                     THEN 1 ELSE 0 END), 0))
            + 0.2 * (SUM(CASE WHEN mp.result = 'win' AND e.date >= CURRENT_DATE - 365
                              THEN 1 ELSE 0 END)::DECIMAL /
                     NULLIF(SUM(CASE WHEN e.date >= CURRENT_DATE - 365
                                     THEN 1 ELSE 0 END), 0)),
            0
        ) AS momentum_score,

        -- Push score: title match frequency + PPV presence + win rate
        COALESCE(
            0.4 * (SUM(CASE WHEN m.title_match AND e.date >= CURRENT_DATE - 90
                            THEN 1 ELSE 0 END)::DECIMAL /
                   NULLIF(SUM(CASE WHEN e.date >= CURRENT_DATE - 90
                                   THEN 1 ELSE 0 END), 0))
            + 0.3 * (SUM(CASE WHEN ev_type.event_type = 'ppv' AND e.date >= CURRENT_DATE - 365
                              THEN 1 ELSE 0 END)::DECIMAL /
                     NULLIF(SUM(CASE WHEN e.date >= CURRENT_DATE - 365
                                     THEN 1 ELSE 0 END), 0))
            + 0.3 * (SUM(CASE WHEN mp.result = 'win' AND e.date >= CURRENT_DATE - 90
                              THEN 1 ELSE 0 END)::DECIMAL /
                     NULLIF(SUM(CASE WHEN e.date >= CURRENT_DATE - 90
                                     THEN 1 ELSE 0 END), 0)),
            0
        ) AS push_score,

        -- Match counts
        SUM(CASE WHEN e.date >= CURRENT_DATE - 30 THEN 1 ELSE 0 END) AS matches_count_30d,
        SUM(CASE WHEN e.date >= CURRENT_DATE - 90 THEN 1 ELSE 0 END) AS matches_count_90d,
        SUM(CASE WHEN e.date >= CURRENT_DATE - 365 THEN 1 ELSE 0 END) AS matches_count_365d,

        -- Title match rate (last 365 days)
        COALESCE(
            SUM(CASE WHEN m.title_match AND e.date >= CURRENT_DATE - 365
                     THEN 1 ELSE 0 END)::DECIMAL /
            NULLIF(SUM(CASE WHEN e.date >= CURRENT_DATE - 365
                            THEN 1 ELSE 0 END), 0),
            0
        ) AS title_match_rate,

        -- PPV win rate (all time)
        COALESCE(
            SUM(CASE WHEN mp.result = 'win' AND ev_type.event_type = 'ppv'
                     THEN 1 ELSE 0 END)::DECIMAL /
            NULLIF(SUM(CASE WHEN ev_type.event_type = 'ppv'
                            THEN 1 ELSE 0 END), 0),
            0
        ) AS ppv_win_rate,

        -- Average match rating
        AVG(m.rating) FILTER (WHERE m.rating IS NOT NULL) AS avg_match_rating

    FROM wrestlers w
    JOIN match_participants mp ON mp.wrestler_id = w.id
    JOIN matches m ON m.id = mp.match_id
    JOIN events e ON e.id = m.event_id
    LEFT JOIN events ev_type ON ev_type.id = m.event_id
    {where_clause}
    GROUP BY w.id

    ON CONFLICT (wrestler_id, as_of_date) DO UPDATE SET
        win_rate_30d = EXCLUDED.win_rate_30d,
        win_rate_90d = EXCLUDED.win_rate_90d,
        win_rate_365d = EXCLUDED.win_rate_365d,
        momentum_score = EXCLUDED.momentum_score,
        push_score = EXCLUDED.push_score,
        matches_count_30d = EXCLUDED.matches_count_30d,
        matches_count_90d = EXCLUDED.matches_count_90d,
        matches_count_365d = EXCLUDED.matches_count_365d,
        title_match_rate = EXCLUDED.title_match_rate,
        ppv_win_rate = EXCLUDED.ppv_win_rate,
        avg_match_rating = EXCLUDED.avg_match_rating
    """

    with conn.cursor() as cur:
        cur.execute(query, params)
        count = cur.rowcount
    conn.commit()

    logger.info("stats_recomputed", wrestlers_updated=count)
    return count


def compute_streaks(conn: psycopg2.extensions.connection) -> int:
    """
    Compute current win/loss streaks for all wrestlers.
    Updates the latest wrestler_stats_rolling row.
    """
    query = """
    WITH recent_results AS (
        SELECT
            mp.wrestler_id,
            mp.result,
            e.date,
            ROW_NUMBER() OVER (
                PARTITION BY mp.wrestler_id ORDER BY e.date DESC, m.match_order DESC
            ) AS rn
        FROM match_participants mp
        JOIN matches m ON m.id = mp.match_id
        JOIN events e ON e.id = m.event_id
        WHERE mp.result IN ('win', 'loss')
    ),
    streaks AS (
        SELECT
            wrestler_id,
            result AS streak_type,
            COUNT(*) AS streak_length
        FROM (
            SELECT
                wrestler_id,
                result,
                rn - ROW_NUMBER() OVER (
                    PARTITION BY wrestler_id, result ORDER BY rn
                ) AS grp
            FROM recent_results
        ) grouped
        WHERE grp = 0
        GROUP BY wrestler_id, result
    )
    UPDATE wrestler_stats_rolling wsr
    SET
        current_win_streak = COALESCE(
            (SELECT streak_length FROM streaks s
             WHERE s.wrestler_id = wsr.wrestler_id AND s.streak_type = 'win'),
            0
        ),
        current_loss_streak = COALESCE(
            (SELECT streak_length FROM streaks s
             WHERE s.wrestler_id = wsr.wrestler_id AND s.streak_type = 'loss'),
            0
        )
    WHERE wsr.as_of_date = CURRENT_DATE
    """

    with conn.cursor() as cur:
        cur.execute(query)
        count = cur.rowcount
    conn.commit()

    logger.info("streaks_computed", wrestlers_updated=count)
    return count
