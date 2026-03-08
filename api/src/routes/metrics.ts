import { Router, Request, Response, NextFunction } from 'express';
import db from '../utils/db';

const router = Router();

// Simple metrics endpoint for monitoring (Prometheus-compatible text format)
router.get('/', async (_req: Request, res: Response, next: NextFunction) => {
  try {
    // Database stats
    const { rows: [dbStats] } = await db.query(
      `SELECT
         (SELECT count(*) FROM wrestlers) AS wrestler_count,
         (SELECT count(*) FROM matches) AS match_count,
         (SELECT count(*) FROM events) AS event_count,
         (SELECT count(*) FROM predictions) AS prediction_count,
         (SELECT max(date) FROM events) AS latest_event_date`
    );

    // Pool stats
    const pool = db as any;
    const poolTotal = pool.totalCount || 0;
    const poolIdle = pool.idleCount || 0;
    const poolWaiting = pool.waitingCount || 0;

    const lines = [
      '# HELP ringside_wrestlers_total Total number of wrestlers in database',
      '# TYPE ringside_wrestlers_total gauge',
      `ringside_wrestlers_total ${dbStats.wrestler_count}`,
      '',
      '# HELP ringside_matches_total Total number of matches in database',
      '# TYPE ringside_matches_total gauge',
      `ringside_matches_total ${dbStats.match_count}`,
      '',
      '# HELP ringside_events_total Total number of events in database',
      '# TYPE ringside_events_total gauge',
      `ringside_events_total ${dbStats.event_count}`,
      '',
      '# HELP ringside_predictions_total Total ML predictions made',
      '# TYPE ringside_predictions_total gauge',
      `ringside_predictions_total ${dbStats.prediction_count}`,
      '',
      '# HELP ringside_db_pool_total Total DB pool connections',
      '# TYPE ringside_db_pool_total gauge',
      `ringside_db_pool_total ${poolTotal}`,
      '',
      '# HELP ringside_db_pool_idle Idle DB pool connections',
      '# TYPE ringside_db_pool_idle gauge',
      `ringside_db_pool_idle ${poolIdle}`,
      '',
      '# HELP ringside_db_pool_waiting Waiting DB pool requests',
      '# TYPE ringside_db_pool_waiting gauge',
      `ringside_db_pool_waiting ${poolWaiting}`,
      '',
    ];

    res.set('Content-Type', 'text/plain; version=0.0.4; charset=utf-8');
    res.send(lines.join('\n'));
  } catch (err) {
    next(err);
  }
});

export default router;
