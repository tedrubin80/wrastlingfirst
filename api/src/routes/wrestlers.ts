import { Router, Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import db from '../utils/db';
import { cached } from '../utils/redis';
import { paginationSchema, buildCursorResponse } from '../utils/pagination';
import { notFound } from '../utils/errors';

const router = Router();

const wrestlerFilterSchema = paginationSchema.extend({
  promotion: z.string().optional(),
  gender: z.enum(['male', 'female']).optional(),
  status: z.enum(['active', 'inactive', 'injured', 'retired', 'deceased', 'free_agent']).optional(),
  brand: z.string().optional(),
  q: z.string().optional(),
});

// GET /api/wrestlers — List/search wrestlers
router.get('/', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const filters = wrestlerFilterSchema.parse(req.query);
    const conditions: string[] = [];
    const params: unknown[] = [];
    let paramIdx = 1;

    if (filters.cursor) {
      conditions.push(`w.id > $${paramIdx++}`);
      params.push(parseInt(filters.cursor, 10));
    }

    if (filters.promotion) {
      conditions.push(`p.abbreviation = $${paramIdx++}`);
      params.push(filters.promotion.toUpperCase());
    }

    if (filters.gender) {
      conditions.push(`w.gender = $${paramIdx++}`);
      params.push(filters.gender);
    }

    if (filters.status) {
      conditions.push(`w.status = $${paramIdx++}`);
      params.push(filters.status);
    }

    if (filters.brand) {
      conditions.push(`w.brand = $${paramIdx++}`);
      params.push(filters.brand);
    }

    if (filters.q) {
      conditions.push(`w.search_vector @@ plainto_tsquery('english', $${paramIdx++})`);
      params.push(filters.q);
    }

    const where = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';

    // Fetch limit + 1 to detect if there are more results
    params.push(filters.limit + 1);

    const { rows } = await db.query(
      `SELECT w.id, w.ring_name, w.real_name, w.gender, w.status, w.brand,
              p.abbreviation AS promotion
       FROM wrestlers w
       LEFT JOIN promotions p ON p.id = w.primary_promotion_id
       ${where}
       ORDER BY w.id ASC
       LIMIT $${paramIdx}`,
      params
    );

    res.json(buildCursorResponse(rows, filters.limit));
  } catch (err) {
    next(err);
  }
});

// GET /api/wrestlers/:id — Wrestler profile with stats summary
router.get('/:id', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const id = parseInt(req.params.id, 10);
    if (isNaN(id)) throw notFound('Wrestler');

    const data = await cached(`wrestler:${id}`, 300, async () => {
      const { rows } = await db.query(
        `SELECT w.id, w.ring_name, w.real_name, w.gender, w.birth_date,
                w.debut_date, w.status, w.brand, w.image_url,
                p.abbreviation AS promotion, p.name AS promotion_name,
                (SELECT count(*) FROM match_participants mp WHERE mp.wrestler_id = w.id) AS total_matches,
                (SELECT count(*) FROM match_participants mp WHERE mp.wrestler_id = w.id AND mp.result = 'win') AS total_wins
         FROM wrestlers w
         LEFT JOIN promotions p ON p.id = w.primary_promotion_id
         WHERE w.id = $1`,
        [id]
      );
      return rows[0] || null;
    });

    if (!data) throw notFound('Wrestler');
    res.json({ data });
  } catch (err) {
    next(err);
  }
});

// GET /api/wrestlers/:id/matches — Paginated match history
router.get('/:id/matches', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const wrestlerId = parseInt(req.params.id, 10);
    if (isNaN(wrestlerId)) throw notFound('Wrestler');

    const filters = paginationSchema.extend({
      year: z.coerce.number().int().optional(),
      promotion: z.string().optional(),
      match_type: z.string().optional(),
      opponent: z.string().optional(),
    }).parse(req.query);

    const conditions: string[] = ['mp.wrestler_id = $1'];
    const params: unknown[] = [wrestlerId];
    let paramIdx = 2;

    if (filters.cursor) {
      conditions.push(`m.id < $${paramIdx++}`);
      params.push(parseInt(filters.cursor, 10));
    }

    if (filters.year) {
      conditions.push(`EXTRACT(YEAR FROM e.date) = $${paramIdx++}`);
      params.push(filters.year);
    }

    if (filters.promotion) {
      conditions.push(`p.abbreviation = $${paramIdx++}`);
      params.push(filters.promotion.toUpperCase());
    }

    if (filters.match_type) {
      conditions.push(`m.match_type = $${paramIdx++}`);
      params.push(filters.match_type);
    }

    params.push(filters.limit + 1);

    const { rows } = await db.query(
      `SELECT m.id, m.match_type, m.stipulation, m.duration_seconds,
              m.title_match, m.rating, m.match_order,
              mp.result,
              e.id AS event_id, e.name AS event_name, e.date AS event_date,
              p.abbreviation AS promotion
       FROM match_participants mp
       JOIN matches m ON m.id = mp.match_id
       JOIN events e ON e.id = m.event_id
       LEFT JOIN promotions p ON p.id = e.promotion_id
       WHERE ${conditions.join(' AND ')}
       ORDER BY e.date DESC, m.match_order DESC
       LIMIT $${paramIdx}`,
      params
    );

    res.json(buildCursorResponse(rows, filters.limit));
  } catch (err) {
    next(err);
  }
});

// GET /api/wrestlers/:id/stats — Computed stats
router.get('/:id/stats', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const id = parseInt(req.params.id, 10);
    if (isNaN(id)) throw notFound('Wrestler');

    const data = await cached(`wrestler-stats:${id}`, 600, async () => {
      // Rolling stats
      const { rows: statsRows } = await db.query(
        `SELECT * FROM wrestler_stats_rolling
         WHERE wrestler_id = $1
         ORDER BY as_of_date DESC LIMIT 1`,
        [id]
      );

      // Match type breakdown
      const { rows: matchTypeRows } = await db.query(
        `SELECT m.match_type,
                count(*) AS total,
                sum(CASE WHEN mp.result = 'win' THEN 1 ELSE 0 END) AS wins
         FROM match_participants mp
         JOIN matches m ON m.id = mp.match_id
         WHERE mp.wrestler_id = $1
         GROUP BY m.match_type
         ORDER BY total DESC`,
        [id]
      );

      return {
        rolling: statsRows[0] || null,
        match_type_breakdown: matchTypeRows,
      };
    });

    res.json({ data });
  } catch (err) {
    next(err);
  }
});

// GET /api/wrestlers/:id/titles — Title reign history
router.get('/:id/titles', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const id = parseInt(req.params.id, 10);
    if (isNaN(id)) throw notFound('Wrestler');

    const { rows } = await db.query(
      `SELECT tr.id, tr.won_date, tr.lost_date, tr.defenses,
              t.name AS title_name, t.id AS title_id,
              p.abbreviation AS promotion
       FROM title_reigns tr
       JOIN titles t ON t.id = tr.title_id
       LEFT JOIN promotions p ON p.id = t.promotion_id
       WHERE tr.wrestler_id = $1
       ORDER BY tr.won_date DESC`,
      [id]
    );

    res.json({ data: rows });
  } catch (err) {
    next(err);
  }
});

export default router;
