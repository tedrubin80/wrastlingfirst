import { Router, Request, Response, NextFunction } from 'express';
import db from '../utils/db';
import { cached } from '../utils/redis';
import { notFound } from '../utils/errors';

const router = Router();

function parseWrestlerId(raw: string): number {
  const id = parseInt(raw, 10);
  if (isNaN(id)) throw notFound('Wrestler');
  return id;
}

// GET /api/wrestlers/:id/charts/win-rate — Monthly rolling win rate
router.get('/:id/charts/win-rate', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const id = parseWrestlerId(req.params.id);

    const data = await cached(`chart:win-rate:${id}`, 3600, async () => {
      const { rows } = await db.query(
        `WITH monthly AS (
           SELECT
             date_trunc('month', e.date)::date AS month,
             count(*) AS total,
             sum(CASE WHEN mp.result = 'win' THEN 1 ELSE 0 END) AS wins
           FROM match_participants mp
           JOIN matches m ON m.id = mp.match_id
           JOIN events e ON e.id = m.event_id
           WHERE mp.wrestler_id = $1
           GROUP BY date_trunc('month', e.date)
           ORDER BY month
         )
         SELECT month, total, wins,
                CASE WHEN total > 0 THEN round(wins::numeric / total, 3) ELSE 0 END AS win_rate
         FROM monthly`,
        [id]
      );
      return rows;
    });

    res.json({ data });
  } catch (err) {
    next(err);
  }
});

// GET /api/wrestlers/:id/charts/momentum — Momentum + push score over time
router.get('/:id/charts/momentum', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const id = parseWrestlerId(req.params.id);

    const data = await cached(`chart:momentum:${id}`, 3600, async () => {
      const { rows } = await db.query(
        `SELECT as_of_date AS date,
                round(momentum_score::numeric, 3) AS momentum,
                round(push_score::numeric, 3) AS push_score
         FROM wrestler_stats_rolling
         WHERE wrestler_id = $1
         ORDER BY as_of_date`,
        [id]
      );
      return rows;
    });

    res.json({ data });
  } catch (err) {
    next(err);
  }
});

// GET /api/wrestlers/:id/charts/streaks — Win/loss streaks over time
router.get('/:id/charts/streaks', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const id = parseWrestlerId(req.params.id);

    const data = await cached(`chart:streaks:${id}`, 3600, async () => {
      const { rows } = await db.query(
        `SELECT as_of_date AS date,
                current_win_streak AS win_streak,
                current_loss_streak AS loss_streak
         FROM wrestler_stats_rolling
         WHERE wrestler_id = $1
         ORDER BY as_of_date`,
        [id]
      );
      return rows;
    });

    res.json({ data });
  } catch (err) {
    next(err);
  }
});

// GET /api/wrestlers/:id/charts/activity — Daily match counts for heatmap
router.get('/:id/charts/activity', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const id = parseWrestlerId(req.params.id);

    const data = await cached(`chart:activity:${id}`, 3600, async () => {
      const { rows } = await db.query(
        `SELECT e.date::text AS date, count(*)::int AS count
         FROM match_participants mp
         JOIN matches m ON m.id = mp.match_id
         JOIN events e ON e.id = m.event_id
         WHERE mp.wrestler_id = $1
           AND e.date >= (current_date - interval '1 year')
         GROUP BY e.date
         ORDER BY e.date`,
        [id]
      );
      return rows;
    });

    res.json({ data });
  } catch (err) {
    next(err);
  }
});

export default router;
