-- Ringside Wrestling Archive — DuckDB SQL recipes
--
-- DuckDB reads parquet directly with no schema setup. Run with:
--   duckdb < duckdb_queries.sql
-- or interactively:
--   duckdb
--   .read duckdb_queries.sql
--
-- All queries assume parquet files are in the current directory.

-- ──────────────────────────────────────────────────────────────────────
-- 1. Sanity check — row counts per table
-- ──────────────────────────────────────────────────────────────────────
SELECT 'promotions'         AS tbl, COUNT(*) AS rows FROM 'promotions.parquet'
UNION ALL SELECT 'wrestlers',         COUNT(*) FROM 'wrestlers.parquet'
UNION ALL SELECT 'wrestler_aliases',  COUNT(*) FROM 'wrestler_aliases.parquet'
UNION ALL SELECT 'events',            COUNT(*) FROM 'events.parquet'
UNION ALL SELECT 'matches',           COUNT(*) FROM 'matches.parquet'
UNION ALL SELECT 'match_participants', COUNT(*) FROM 'match_participants.parquet'
UNION ALL SELECT 'titles',            COUNT(*) FROM 'titles.parquet'
UNION ALL SELECT 'title_reigns',      COUNT(*) FROM 'title_reigns.parquet'
UNION ALL SELECT 'alignment_turns',   COUNT(*) FROM 'alignment_turns.parquet'
ORDER BY rows DESC;

-- ──────────────────────────────────────────────────────────────────────
-- 2. Top 20 wrestlers by total matches
-- ──────────────────────────────────────────────────────────────────────
SELECT w.ring_name, COUNT(*) AS matches
FROM 'match_participants.parquet' mp
JOIN 'wrestlers.parquet' w ON w.id = mp.wrestler_id
GROUP BY 1
ORDER BY 2 DESC
LIMIT 20;

-- ──────────────────────────────────────────────────────────────────────
-- 3. Matches per year by promotion (last 30 years)
-- ──────────────────────────────────────────────────────────────────────
SELECT
    EXTRACT(YEAR FROM e.date) AS year,
    p.abbreviation             AS promo,
    COUNT(*)                   AS matches
FROM 'matches.parquet' m
JOIN 'events.parquet'     e ON e.id = m.event_id
JOIN 'promotions.parquet' p ON p.id = e.promotion_id
WHERE e.date >= CURRENT_DATE - INTERVAL 30 YEAR
GROUP BY 1, 2
ORDER BY 1 DESC, 3 DESC;

-- ──────────────────────────────────────────────────────────────────────
-- 4. Career win rates (≥50 matches) — the kayfabe distribution
-- ──────────────────────────────────────────────────────────────────────
SELECT
    w.ring_name,
    COUNT(*)                                       AS matches,
    AVG((mp.result = 'win')::INTEGER)::DECIMAL(4,3) AS win_rate
FROM 'match_participants.parquet' mp
JOIN 'wrestlers.parquet' w ON w.id = mp.wrestler_id
GROUP BY w.ring_name
HAVING COUNT(*) >= 50
ORDER BY win_rate DESC
LIMIT 30;

-- ──────────────────────────────────────────────────────────────────────
-- 5. Longest title reigns
-- ──────────────────────────────────────────────────────────────────────
SELECT
    w.ring_name,
    t.name                                                    AS title,
    tr.won_date,
    COALESCE(tr.lost_date, CURRENT_DATE) - tr.won_date         AS length_days,
    tr.defenses
FROM 'title_reigns.parquet' tr
JOIN 'wrestlers.parquet' w ON w.id = tr.wrestler_id
JOIN 'titles.parquet'    t ON t.id = tr.title_id
ORDER BY length_days DESC
LIMIT 25;

-- ──────────────────────────────────────────────────────────────────────
-- 6. Highest-rated matches (Cagematch crowd ratings)
-- ──────────────────────────────────────────────────────────────────────
SELECT
    e.date,
    e.name      AS event,
    p.abbreviation AS promo,
    m.match_type,
    m.rating
FROM 'matches.parquet' m
JOIN 'events.parquet'     e ON e.id = m.event_id
JOIN 'promotions.parquet' p ON p.id = e.promotion_id
WHERE m.rating IS NOT NULL
ORDER BY m.rating DESC, e.date DESC
LIMIT 25;

-- ──────────────────────────────────────────────────────────────────────
-- 7. Royal Rumble winners by year
-- ──────────────────────────────────────────────────────────────────────
SELECT
    EXTRACT(YEAR FROM e.date) AS year,
    w.ring_name                AS winner
FROM 'matches.parquet' m
JOIN 'events.parquet'             e ON e.id = m.event_id
JOIN 'match_participants.parquet' mp ON mp.match_id = m.id AND mp.result = 'win'
JOIN 'wrestlers.parquet'           w ON w.id = mp.wrestler_id
WHERE m.match_type = 'royal_rumble'
ORDER BY year DESC;

-- ──────────────────────────────────────────────────────────────────────
-- 8. Head-to-head — most-wrestled matchup
-- ──────────────────────────────────────────────────────────────────────
WITH singles AS (
    SELECT match_id
    FROM 'match_participants.parquet'
    GROUP BY match_id
    HAVING COUNT(*) = 2
),
pairs AS (
    SELECT
        s.match_id,
        LEAST(mp1.wrestler_id, mp2.wrestler_id)    AS w_a,
        GREATEST(mp1.wrestler_id, mp2.wrestler_id) AS w_b
    FROM singles s
    JOIN 'match_participants.parquet' mp1 ON mp1.match_id = s.match_id
    JOIN 'match_participants.parquet' mp2 ON mp2.match_id = s.match_id AND mp1.id < mp2.id
)
SELECT
    wa.ring_name AS wrestler_a,
    wb.ring_name AS wrestler_b,
    COUNT(*)     AS encounters
FROM pairs p
JOIN 'wrestlers.parquet' wa ON wa.id = p.w_a
JOIN 'wrestlers.parquet' wb ON wb.id = p.w_b
GROUP BY 1, 2
ORDER BY 3 DESC
LIMIT 25;

-- ──────────────────────────────────────────────────────────────────────
-- 9. Match-type win-rate variance (which formats are predictable?)
-- ──────────────────────────────────────────────────────────────────────
SELECT
    m.match_type,
    COUNT(*)                                                AS matches,
    AVG((mp.result = 'win')::INTEGER)::DECIMAL(4,3)         AS win_rate,
    STDDEV_SAMP((mp.result = 'win')::INTEGER)::DECIMAL(4,3) AS stddev
FROM 'matches.parquet' m
JOIN 'match_participants.parquet' mp ON mp.match_id = m.id
GROUP BY 1
HAVING matches > 100
ORDER BY stddev DESC;

-- ──────────────────────────────────────────────────────────────────────
-- 10. Use the denormalized match_view for quick ML-ready slices
-- ──────────────────────────────────────────────────────────────────────
SELECT
    promotion_abbr,
    COUNT(*)                                            AS matches,
    AVG(rating)                                         AS avg_rating,
    AVG((result = 'win')::INTEGER)                      AS win_rate
FROM 'match_view.parquet'
WHERE year >= 2020
  AND is_singles
GROUP BY 1
ORDER BY 2 DESC;
