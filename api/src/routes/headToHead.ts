import { Router, Request, Response, NextFunction } from 'express';
import db from '../utils/db';
import { cached } from '../utils/redis';
import { notFound } from '../utils/errors';

const router = Router();

// GET /api/head-to-head/:id1/:id2 — Head-to-head record and match history
router.get('/:id1/:id2', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const id1 = parseInt(req.params.id1, 10);
    const id2 = parseInt(req.params.id2, 10);
    if (isNaN(id1) || isNaN(id2)) throw notFound('Wrestler');

    const data = await cached(`h2h:${Math.min(id1, id2)}:${Math.max(id1, id2)}`, 600, async () => {
      // Get wrestler info
      const { rows: wrestlers } = await db.query(
        `SELECT id, ring_name, image_url FROM wrestlers WHERE id = ANY($1)`,
        [[id1, id2]]
      );

      if (wrestlers.length < 2) return null;

      // Find all matches where both wrestlers participated
      const { rows: matches } = await db.query(
        `SELECT m.id, m.match_type, m.stipulation, m.duration_seconds,
                m.title_match, m.rating,
                e.name AS event_name, e.date AS event_date,
                p.abbreviation AS promotion,
                mp1.result AS wrestler1_result,
                mp2.result AS wrestler2_result
         FROM match_participants mp1
         JOIN match_participants mp2 ON mp2.match_id = mp1.match_id AND mp2.wrestler_id = $2
         JOIN matches m ON m.id = mp1.match_id
         JOIN events e ON e.id = m.event_id
         LEFT JOIN promotions p ON p.id = e.promotion_id
         WHERE mp1.wrestler_id = $1
         ORDER BY e.date DESC`,
        [id1, id2]
      );

      const w1Wins = matches.filter((m) => m.wrestler1_result === 'win').length;
      const w2Wins = matches.filter((m) => m.wrestler2_result === 'win').length;
      const draws = matches.filter((m) =>
        m.wrestler1_result === 'draw' || m.wrestler1_result === 'no_contest'
      ).length;

      return {
        wrestler1: wrestlers.find((w) => w.id === id1),
        wrestler2: wrestlers.find((w) => w.id === id2),
        summary: {
          total_matches: matches.length,
          wrestler1_wins: w1Wins,
          wrestler2_wins: w2Wins,
          draws,
        },
        matches,
      };
    });

    if (!data) throw notFound('Wrestler');
    res.json({ data });
  } catch (err) {
    next(err);
  }
});

export default router;
