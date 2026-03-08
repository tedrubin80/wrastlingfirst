import { Router, Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import db from '../utils/db';
import { paginationSchema, buildCursorResponse } from '../utils/pagination';
import { notFound } from '../utils/errors';

const router = Router();

const matchFilterSchema = paginationSchema.extend({
  date_from: z.string().optional(),
  date_to: z.string().optional(),
  promotion: z.string().optional(),
  match_type: z.string().optional(),
  wrestler: z.string().optional(),
});

// GET /api/matches — Search matches
router.get('/', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const filters = matchFilterSchema.parse(req.query);
    const conditions: string[] = [];
    const params: unknown[] = [];
    let paramIdx = 1;

    if (filters.cursor) {
      conditions.push(`m.id < $${paramIdx++}`);
      params.push(parseInt(filters.cursor, 10));
    }

    if (filters.date_from) {
      conditions.push(`e.date >= $${paramIdx++}`);
      params.push(filters.date_from);
    }

    if (filters.date_to) {
      conditions.push(`e.date <= $${paramIdx++}`);
      params.push(filters.date_to);
    }

    if (filters.promotion) {
      conditions.push(`p.abbreviation = $${paramIdx++}`);
      params.push(filters.promotion.toUpperCase());
    }

    if (filters.match_type) {
      conditions.push(`m.match_type = $${paramIdx++}`);
      params.push(filters.match_type);
    }

    if (filters.wrestler) {
      conditions.push(`EXISTS (
        SELECT 1 FROM match_participants mp2
        JOIN wrestlers w2 ON w2.id = mp2.wrestler_id
        WHERE mp2.match_id = m.id
        AND w2.search_vector @@ plainto_tsquery('english', $${paramIdx++})
      )`);
      params.push(filters.wrestler);
    }

    const where = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
    params.push(filters.limit + 1);

    const { rows } = await db.query(
      `SELECT m.id, m.match_type, m.stipulation, m.duration_seconds,
              m.title_match, m.rating, m.match_order,
              e.id AS event_id, e.name AS event_name, e.date AS event_date,
              p.abbreviation AS promotion
       FROM matches m
       JOIN events e ON e.id = m.event_id
       LEFT JOIN promotions p ON p.id = e.promotion_id
       ${where}
       ORDER BY e.date DESC, m.match_order DESC
       LIMIT $${paramIdx}`,
      params
    );

    res.json(buildCursorResponse(rows, filters.limit));
  } catch (err) {
    next(err);
  }
});

// GET /api/matches/:id — Full match detail with all participants
router.get('/:id', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const id = parseInt(req.params.id, 10);
    if (isNaN(id)) throw notFound('Match');

    const { rows: matchRows } = await db.query(
      `SELECT m.id, m.match_type, m.stipulation, m.duration_seconds,
              m.title_match, m.rating, m.match_order,
              e.id AS event_id, e.name AS event_name, e.date AS event_date,
              e.venue, e.city, e.country,
              p.abbreviation AS promotion
       FROM matches m
       JOIN events e ON e.id = m.event_id
       LEFT JOIN promotions p ON p.id = e.promotion_id
       WHERE m.id = $1`,
      [id]
    );

    if (matchRows.length === 0) throw notFound('Match');

    const { rows: participants } = await db.query(
      `SELECT mp.result, mp.team_number, mp.entry_order, mp.elimination_order,
              w.id AS wrestler_id, w.ring_name, w.image_url
       FROM match_participants mp
       JOIN wrestlers w ON w.id = mp.wrestler_id
       WHERE mp.match_id = $1
       ORDER BY mp.team_number, mp.entry_order`,
      [id]
    );

    res.json({
      data: {
        ...matchRows[0],
        participants,
      },
    });
  } catch (err) {
    next(err);
  }
});

export default router;
