import { Router, Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import logger from '../utils/logger';

const router = Router();

const ML_SERVICE_URL = process.env.ML_SERVICE_URL || 'http://localhost:8000';

const predictSchema = z.object({
  wrestler_ids: z.array(z.number().int()).min(2).max(8),
  match_type: z.string().optional(),
  event_tier: z.enum(['ppv', 'weekly_tv', 'special']).optional(),
  title_match: z.boolean().optional(),
});

// POST /api/predict — Proxy to ML prediction service
router.post('/', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const input = predictSchema.parse(req.body);

    // Try the ML service first
    try {
      const mlResponse = await fetch(`${ML_SERVICE_URL}/predict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          wrestler_ids: input.wrestler_ids,
          match_type: input.match_type || 'singles',
          event_tier: input.event_tier || 'weekly_tv',
          title_match: input.title_match || false,
        }),
      });

      if (mlResponse.ok) {
        const data = await mlResponse.json();
        res.json({ data });
        return;
      }

      logger.warn({ status: mlResponse.status }, 'ML service returned error');
    } catch (err) {
      logger.warn('ML service unavailable, falling back to stub');
    }

    // Fallback: equal probabilities
    const n = input.wrestler_ids.length;
    res.json({
      data: {
        probabilities: input.wrestler_ids.map((id) => ({
          wrestler_id: id,
          win_probability: Math.round((1 / n) * 100) / 100,
          confidence: 0,
        })),
        factors: [],
        model_version: 'fallback-stub',
        message: 'ML service unavailable — returning equal probabilities.',
      },
    });
  } catch (err) {
    next(err);
  }
});

export default router;
