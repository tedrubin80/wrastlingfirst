import express from 'express';
import cors from 'cors';
import pinoHttp from 'pino-http';
import logger from './utils/logger';
import { errorHandler } from './utils/errors';
import wrestlersRouter from './routes/wrestlers';
import matchesRouter from './routes/matches';
import eventsRouter from './routes/events';
import headToHeadRouter from './routes/headToHead';
import titlesRouter from './routes/titles';
import predictRouter from './routes/predict';
import chartsRouter from './routes/charts';
import metricsRouter from './routes/metrics';

const app = express();
const port = parseInt(process.env.PORT || '3001', 10);

// Middleware
app.use(cors({
  origin: process.env.FRONTEND_URL || 'http://localhost:3000',
  credentials: true,
}));
app.use(express.json());
app.use(pinoHttp({ logger }));

// Health check
app.get('/api/health', (_req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Routes
app.use('/api/wrestlers', wrestlersRouter);
app.use('/api/matches', matchesRouter);
app.use('/api/events', eventsRouter);
app.use('/api/head-to-head', headToHeadRouter);
app.use('/api/titles', titlesRouter);
app.use('/api/predict', predictRouter);
app.use('/api/wrestlers', chartsRouter);

app.use('/api/metrics', metricsRouter);

// Error handler (must be last)
app.use(errorHandler);

app.listen(port, () => {
  logger.info({ port }, 'Ringside API listening');
});

export default app;
