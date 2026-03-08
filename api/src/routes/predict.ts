import { Router, Request, Response, NextFunction } from 'express';
import { z } from 'zod';

const router = Router();

const predictSchema = z.object({
  wrestler_ids: z.array(z.number().int()).min(2).max(8),
  match_type: z.string().optional(),
  event_tier: z.enum(['ppv', 'weekly_tv', 'special']).optional(),
  title_match: z.boolean().optional(),
});

// POST /api/predict — ML prediction stub (Phase 3)
router.post('/', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const input = predictSchema.parse(req.body);

    // Stub response until ML service is built in Phase 3
    const n = input.wrestler_ids.length;
    const probabilities = input.wrestler_ids.map((id, i) => ({
      wrestler_id: id,
      win_probability: Math.round((1 / n) * 100) / 100,
      confidence: 0,
    }));

    res.json({
      data: {
        probabilities,
        model_version: 'stub-v0',
        factors: [],
        message: 'Prediction engine not yet trained — returning equal probabilities.',
      },
    });
  } catch (err) {
    next(err);
  }
});

export default router;
