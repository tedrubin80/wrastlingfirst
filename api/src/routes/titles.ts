import { Router, Request, Response, NextFunction } from 'express';
import db from '../utils/db';
import { notFound } from '../utils/errors';

const router = Router();

// GET /api/titles — All championships with current holders
router.get('/', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { rows } = await db.query(
      `SELECT t.id, t.name, t.established, t.retired, t.active,
              p.abbreviation AS promotion,
              w.id AS current_holder_id,
              w.ring_name AS current_holder
       FROM titles t
       LEFT JOIN promotions p ON p.id = t.promotion_id
       LEFT JOIN title_reigns tr ON tr.title_id = t.id AND tr.lost_date IS NULL
       LEFT JOIN wrestlers w ON w.id = tr.wrestler_id
       ORDER BY t.active DESC, p.abbreviation, t.name`
    );

    res.json({ data: rows });
  } catch (err) {
    next(err);
  }
});

// GET /api/titles/:id/history — Full title lineage
router.get('/:id/history', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const id = parseInt(req.params.id, 10);
    if (isNaN(id)) throw notFound('Title');

    const { rows: titleRows } = await db.query(
      `SELECT t.id, t.name, t.established, t.retired, t.active,
              p.abbreviation AS promotion
       FROM titles t
       LEFT JOIN promotions p ON p.id = t.promotion_id
       WHERE t.id = $1`,
      [id]
    );

    if (titleRows.length === 0) throw notFound('Title');

    const { rows: reigns } = await db.query(
      `SELECT tr.id, tr.won_date, tr.lost_date, tr.defenses,
              w.id AS wrestler_id, w.ring_name, w.image_url,
              we.name AS won_at_event, le.name AS lost_at_event
       FROM title_reigns tr
       JOIN wrestlers w ON w.id = tr.wrestler_id
       LEFT JOIN events we ON we.id = tr.won_at_event_id
       LEFT JOIN events le ON le.id = tr.lost_at_event_id
       WHERE tr.title_id = $1
       ORDER BY tr.won_date DESC`,
      [id]
    );

    res.json({
      data: {
        ...titleRows[0],
        reigns,
      },
    });
  } catch (err) {
    next(err);
  }
});

export default router;
