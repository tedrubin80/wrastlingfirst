import { Router, Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import db from '../utils/db';
import { cached } from '../utils/redis';
import { paginationSchema, buildCursorResponse } from '../utils/pagination';
import { notFound } from '../utils/errors';

const router = Router();

const eventFilterSchema = paginationSchema.extend({
  promotion: z.string().optional(),
  year: z.coerce.number().int().optional(),
  event_type: z.enum(['ppv', 'weekly_tv', 'special', 'house_show', 'tournament']).optional(),
  q: z.string().optional(),
});

// GET /api/events — List/search events
router.get('/', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const filters = eventFilterSchema.parse(req.query);
    const conditions: string[] = [];
    const params: unknown[] = [];
    let paramIdx = 1;

    if (filters.cursor) {
      conditions.push(`e.id < $${paramIdx++}`);
      params.push(parseInt(filters.cursor, 10));
    }

    if (filters.promotion) {
      conditions.push(`p.abbreviation = $${paramIdx++}`);
      params.push(filters.promotion.toUpperCase());
    }

    if (filters.year) {
      conditions.push(`EXTRACT(YEAR FROM e.date) = $${paramIdx++}`);
      params.push(filters.year);
    }

    if (filters.event_type) {
      conditions.push(`e.event_type = $${paramIdx++}`);
      params.push(filters.event_type);
    }

    if (filters.q) {
      conditions.push(`e.search_vector @@ plainto_tsquery('english', $${paramIdx++})`);
      params.push(filters.q);
    }

    const where = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
    params.push(filters.limit + 1);

    const { rows } = await db.query(
      `SELECT e.id, e.name, e.date, e.venue, e.city, e.country,
              e.event_type,
              p.abbreviation AS promotion,
              (SELECT count(*) FROM matches m WHERE m.event_id = e.id) AS match_count
       FROM events e
       LEFT JOIN promotions p ON p.id = e.promotion_id
       ${where}
       ORDER BY e.date DESC
       LIMIT $${paramIdx}`,
      params
    );

    res.json(buildCursorResponse(rows, filters.limit));
  } catch (err) {
    next(err);
  }
});

// GET /api/events/:id — Full event card with all matches
router.get('/:id', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const id = parseInt(req.params.id, 10);
    if (isNaN(id)) throw notFound('Event');

    const data = await cached(`event:${id}`, 600, async () => {
      const { rows: eventRows } = await db.query(
        `SELECT e.id, e.name, e.date, e.venue, e.city, e.state, e.country,
                e.event_type,
                p.abbreviation AS promotion, p.name AS promotion_name
         FROM events e
         LEFT JOIN promotions p ON p.id = e.promotion_id
         WHERE e.id = $1`,
        [id]
      );

      if (eventRows.length === 0) return null;

      const { rows: matches } = await db.query(
        `SELECT m.id, m.match_order, m.match_type, m.stipulation,
                m.duration_seconds, m.title_match, m.rating,
                json_agg(json_build_object(
                  'wrestler_id', w.id,
                  'ring_name', w.ring_name,
                  'result', mp.result,
                  'team_number', mp.team_number
                ) ORDER BY mp.team_number, mp.entry_order) AS participants
         FROM matches m
         LEFT JOIN match_participants mp ON mp.match_id = m.id
         LEFT JOIN wrestlers w ON w.id = mp.wrestler_id
         WHERE m.event_id = $1
         GROUP BY m.id
         ORDER BY m.match_order ASC`,
        [id]
      );

      return { ...eventRows[0], matches };
    });

    if (!data) throw notFound('Event');
    res.json({ data });
  } catch (err) {
    next(err);
  }
});

export default router;
