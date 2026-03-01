# Ringside Analytics — Engineering Plan

> **Status:** Planning
> **Author:** Theodore M. Rubin
> **Version:** 1.0 — February 2026
> **Created:** 2026-03-01
> **Stack:** Next.js 14 / Express / FastAPI / PostgreSQL 16 / Redis 7 / XGBoost / Docker
> **Source:** [Site Plan (Google Doc)](https://docs.google.com/document/d/11huygNDGitqTDSsQPlAINoOYCETYXjWZ/edit?usp=sharing)

---

## Project Overview

Full-stack web application analyzing 40+ years of professional wrestling match data (1980–present). Covers WWE (Raw, SmackDown), NXT, AEW, and historical promotions (WCW, ECW, TNA).

**Core capabilities:**
1. ML-powered match outcome predictions with explainable factors
2. Historical match search & browse (40+ years)
3. Data visualizations — win streaks, momentum curves, career trends, head-to-head records

**Key insight:** Predictions are based on **booking patterns** (push momentum, title trajectories, win streaks, promotion tendencies) — not athletic performance. Wrestling outcomes are scripted, so the model learns what bookers tend to do, not who is the "better" wrestler.

**Estimated data volume:** 200,000–400,000 matches, 10,000–15,000 unique wrestlers after entity resolution.

---

## Prerequisites / Inputs

- [x] `wrestlers_roster_2026.csv` — 354 wrestlers (172 WWE, 182 AEW) with name, org, brand, gender, status
- [x] Site Plan Document — [Google Doc](https://docs.google.com/document/d/11huygNDGitqTDSsQPlAINoOYCETYXjWZ/edit?usp=sharing) (Version 1.0, Feb 2026)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     FRONTEND                            │
│              Next.js 14 (App Router)                    │
│         Tailwind CSS + shadcn/ui + Recharts             │
│                Dark theme, mobile-first                 │
└──────────────────────┬──────────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
┌──────────────────┐     ┌────────────────────┐
│   Express API    │     │  FastAPI (ML)       │
│   (Node/TS)      │     │  (Python 3.11+)    │
│                  │     │                    │
│  REST endpoints  │     │  POST /predict     │
│  Full-text search│     │  Feature compute   │
│  Redis caching   │     │  Model inference   │
└────────┬─────────┘     └────────┬───────────┘
         │                        │
         └──────────┬─────────────┘
                    ▼
          ┌──────────────────┐
          │  PostgreSQL 16   │◄── Scraper/ETL pipeline (Python)
          │  + Redis 7       │◄── Celery beat (nightly refresh)
          └──────────────────┘
```

---

## Phase 1: Data Foundation

**Goal:** PostgreSQL database, scraping pipeline, historical data populated.

### 1.1 — Database Schema (`schema.sql`)

| Table | Purpose |
|-------|---------|
| `wrestlers` | Master registry — id, ring_name, real_name, gender, birth_date, debut_date, status, primary_promotion_id |
| `wrestler_aliases` | Name mapping across eras/promotions — wrestler_id, alias, promotion_id, active_from, active_to |
| `promotions` | WWE, AEW, WCW, ECW, TNA, NXT — id, name, abbreviation, founded, defunct, parent_org |
| `events` | PPVs, TV episodes, house shows — id, name, promotion_id, date, venue, city, state, country, event_type ENUM |
| `matches` | Individual matches — id, event_id, match_order, match_type ENUM, stipulation, duration_seconds, title_match, rating |
| `match_participants` | Junction — match_id, wrestler_id, team_number, result ENUM, entry_order, elimination_order |
| `titles` | Championship registry — id, name, promotion_id, established, retired, active |
| `title_reigns` | Reign history — title_id, wrestler_id, won_date, lost_date, defenses, won/lost_at_event_id |
| `wrestler_stats_rolling` | Pre-computed ML features — wrestler_id, as_of_date, win rates (30/90/365d), streaks, momentum, push score |
| `predictions` | Cached ML results — wrestler_ids jsonb, context jsonb, probabilities jsonb, model_version, created_at |

**ENUMs:**
- `match_type`: singles, tag_team, triple_threat, fatal_four_way, battle_royal, royal_rumble, ladder, tlc, hell_in_a_cell, cage, elimination_chamber, iron_man, i_quit, last_man_standing, tables, handicap, gauntlet, other
- `event_type`: ppv, weekly_tv, special, house_show, tournament
- `result`: win, loss, draw, no_contest, dq, countout

**Indexes:** Composite indexes on common query patterns (wrestler+date, event+promotion, match participants).

### 1.2 — Cagematch Scraper (`scraper/`)

Python scraper using `requests` + `BeautifulSoup`:
- Scrape by promotion and year range
- Extract: event name, date, venue, match card (participants, match type, result, duration, rating)
- Rate limit: 1 req/sec with exponential backoff
- Local HTML cache to avoid redundant requests
- Pagination handling
- Structured JSON output mapping to schema
- Configurable date range and promotion
- Respect robots.txt, attribute data sources

**Additional data sources (future):** ProFightDB, Internet Wrestling Database, WWE API, AEW results sites, Kaggle datasets.

### 1.3 — ETL Pipeline (`etl/`)

- Parse scraped JSON → normalized DB records
- Entity resolution: fuzzy match wrestler names via `rapidfuzz` against aliases table
- Log unresolved names for manual review
- Standardize match types to ENUM vocabulary
- Upsert logic: `ON CONFLICT` for idempotent loads
- Post-load: recompute `wrestler_stats_rolling` for affected wrestlers
- Validation: row counts, duplicates, unresolved names

### 1.4 — Docker Setup

`docker-compose.yml` services:
- PostgreSQL 16 (persistent volume)
- Redis 7 (persistent volume)
- Scraper/ETL as one-off job container

### Phase 1 Deliverables
- [ ] `schema.sql` — Full DDL
- [ ] `seed.py` — CSV → wrestlers/promotions loader
- [ ] `scraper/` — Python scraping package
- [ ] `etl/` — Transform and load scripts
- [ ] `docker-compose.yml`
- [ ] `README.md`

---

## Phase 2: API & Search

**Goal:** REST API + Next.js frontend for browsing historical match data.

### 2.1 — Express API (`api/`)

Node.js + Express + TypeScript (strict mode)

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/wrestlers` | List/search (filters: promotion, gender, status, era, query) |
| GET | `/api/wrestlers/:id` | Profile with career stats summary |
| GET | `/api/wrestlers/:id/matches` | Paginated match history (filters: year, promotion, match_type, opponent) |
| GET | `/api/wrestlers/:id/stats` | Win rates, streaks, momentum, match-type breakdown |
| GET | `/api/wrestlers/:id/titles` | Title reign history |
| GET | `/api/matches` | Search matches (filters: date range, promotion, match_type, wrestler) |
| GET | `/api/matches/:id` | Full match detail with all participants |
| GET | `/api/events` | List/search events (filters: promotion, year, event_type) |
| GET | `/api/events/:id` | Full event card with all matches |
| GET | `/api/head-to-head/:id1/:id2` | Head-to-head record and series stats |
| GET | `/api/titles` | All championships with current holders |
| GET | `/api/titles/:id/history` | Full title lineage |
| POST | `/api/predict` | ML prediction (stub until Phase 3) |

**Requirements:**
- Cursor-based pagination on all list endpoints
- Redis caching on hot endpoints
- Full-text search via PostgreSQL `tsvector`
- Input validation with `zod`
- Consistent error response format
- Request logging with `morgan` / `pino`
- CORS for Next.js frontend

### 2.2 — Next.js Frontend (`frontend/`)

Next.js 14 (App Router) + Tailwind CSS + shadcn/ui

**Pages:**

| Route | Description |
|-------|-------------|
| `/` | Home — search bar, featured predictions, recent events |
| `/wrestlers` | Directory with filters and search |
| `/wrestlers/[id]` | Profile — stats, match history, title timeline |
| `/events` | Event browser by promotion and year |
| `/events/[id]` | Full event card view |
| `/matches/[id]` | Individual match detail |
| `/predict` | Prediction tool (selector shell, completed Phase 3) |
| `/head-to-head` | Wrestler comparison tool |

**Design:**
- Dark theme, accent colors (ESPN/FiveThirtyEight analytics aesthetic)
- Data-forward, professional — not campy
- Responsive mobile-first
- React Server Components for data-heavy pages
- Reusable typeahead wrestler search component

### Phase 2 Deliverables
- [ ] `api/` — Express API with all endpoints
- [ ] `frontend/` — Next.js application
- [ ] Updated `docker-compose.yml` with API + frontend services
- [ ] Updated `README.md`

---

## Phase 3: ML Prediction Engine

**Goal:** Train and deploy the match outcome prediction model.

### 3.1 — Feature Engineering (`ml/features.py`)

Per wrestler, per match:

| Category | Features |
|----------|----------|
| Win Momentum | Win rate 30/90/365 days, current win streak, current loss streak |
| Title Proximity | Days since last title match, is_champion, defenses count, title match win rate |
| Event Context | PPV vs TV flag, card position (0–1), event significance tier |
| Match Type | Historical win rate for specific match type |
| Head-to-Head | Prior record vs opponent, days since last matchup |
| Career Phase | Years active, matches in last 90d (activity level), days since last match |
| Promotion Context | Promotion-specific win rate, recently changed promotions flag |
| Narrative Arc | Storyline indicators — feud duration, revenge match flag, debut/return flag |

Output: feature matrix (one row per match participant), target = `won` (1/0).

### 3.2 — Model Training (`ml/train.py`)

- Temporal split: train < 2024, validate 2024, test 2025+
- Baseline: Logistic Regression (interpretability)
- Primary: XGBoost gradient boosted trees
- Optional: LSTM for temporal/sequential booking patterns
- Metrics: Accuracy, AUC-ROC, log loss, calibration curves
- Feature importance extraction
- Target accuracy: 65–70%
- Experiment tracking with MLflow

### 3.3 — Prediction Service (`ml/service/`)

FastAPI service:
- Input: wrestler IDs + optional context (match_type, event_tier, title_match)
- Computes real-time features from latest stats
- Runs model inference
- Returns: win probabilities, confidence, top 5 contributing factors (human-readable)
- Redis caching (key = sorted wrestler IDs + context hash)

### 3.4 — Prediction UI

Complete `/predict` page:
- Typeahead wrestler selector (2–8 wrestlers)
- Context dropdowns (match type, event tier, title match toggle)
- Results: win probability bar chart, contributing factor cards, historical matchup table
- Skeleton loading states
- Shareable prediction URLs (query params)

### Phase 3 Deliverables
- [ ] `ml/features.py`
- [ ] `ml/train.py`
- [ ] `ml/service/` — FastAPI prediction service
- [ ] Updated frontend with prediction UI
- [ ] Updated `docker-compose.yml` with ML service
- [ ] Model performance report

---

## Phase 4: Visualizations & Polish

**Goal:** Interactive charts, automated data refresh, performance, monitoring.

### 4.1 — Chart Components (`components/charts/`)

Using Recharts — all responsive, themed, with tooltips and skeleton states:

| Component | Type | Description |
|-----------|------|-------------|
| `WinRateTimeline` | Line chart | Rolling 90-day win % over career |
| `MomentumCurve` | Area chart | Composite push/momentum score |
| `StreakHistory` | Bar chart | Win/loss streaks by year |
| `MatchTypeRadar` | Radar chart | Win rates across match types |
| `HeadToHeadBar` | Stacked horizontal bar | Series record |
| `TitleTimeline` | Gantt-style | Championship reigns on timeline |
| `ActivityHeatmap` | Calendar heatmap | Match frequency by week |

### 4.2 — Nightly Data Refresh

Celery beat schedule:
- **Nightly (3 AM EST):** Scrape latest results → ETL → recompute stats → invalidate caches
- **Weekly (Sunday):** Full model retrain with latest data

Active promotions: WWE Raw, SmackDown, NXT, AEW Dynamite/Collision/Rampage

### 4.3 — Performance & SEO

- PostgreSQL query optimization (EXPLAIN ANALYZE, missing indexes)
- Next.js ISR for wrestler profiles, static for old events
- Image optimization (next/image)
- Structured data (JSON-LD) for wrestlers and events
- Sitemap generation
- OpenGraph meta tags (prediction pages especially)

### 4.4 — Monitoring

- Prometheus metrics on API (request count, latency, error rate)
- Grafana dashboard
- Model drift detection
- Scraper failure alerts

### Phase 4 Deliverables
- [ ] `components/charts/` — All visualization components
- [ ] Celery task definitions and beat schedule
- [ ] Performance optimization report
- [ ] Monitoring stack configuration
- [ ] Final `docker-compose.yml` with all services
- [ ] Deployment documentation

---

## Coding Standards

| Area | Standard |
|------|----------|
| Node.js / React | TypeScript strict mode |
| Python | 3.11+ with type hints |
| SQL | Parameterized queries only — never string concatenation |
| Error handling | try/catch on every async function, meaningful messages |
| Logging | Structured JSON — pino (Node), structlog (Python) |
| Testing | Jest (API), pytest (Python), React Testing Library (components) |
| Git | Conventional commits, feature branches, PR-based |
| Docker | Multi-stage builds (prod), hot reload (dev) |
| Comments | Explain *why*, not *what* |

---

## Project Structure (Target)

```
/var/www/wrastling/
├── docker-compose.yml
├── schema.sql
├── seed.py
├── PLAN.md
├── README.md
├── scraper/
│   ├── __init__.py
│   ├── cagematch.py
│   ├── config.py
│   └── cache/
├── etl/
│   ├── __init__.py
│   ├── transform.py
│   ├── load.py
│   └── entity_resolution.py
├── api/
│   ├── package.json
│   ├── tsconfig.json
│   ├── src/
│   │   ├── index.ts
│   │   ├── routes/
│   │   ├── middleware/
│   │   ├── services/
│   │   └── utils/
│   └── tests/
├── frontend/
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.ts
│   ├── app/
│   │   ├── page.tsx
│   │   ├── wrestlers/
│   │   ├── events/
│   │   ├── matches/
│   │   ├── predict/
│   │   └── head-to-head/
│   ├── components/
│   │   ├── charts/
│   │   ├── ui/
│   │   └── search/
│   └── lib/
├── ml/
│   ├── features.py
│   ├── train.py
│   ├── service/
│   │   ├── main.py
│   │   ├── predict.py
│   │   └── requirements.txt
│   └── models/
└── monitoring/
    ├── prometheus.yml
    └── grafana/
```

---

## Open Questions / Decisions Needed

1. **Wrestler photos** — Source? Scrape from Cagematch or use placeholder silhouettes?
2. **Authentication** — Any user accounts needed, or fully public?
3. **Deployment domain** — What domain/subdomain will this live on?
4. **SSL/Proxy** — Nginx reverse proxy in front, or handled elsewhere?
5. **Data backfill scope** — Full 1980–present, or start with a narrower window (e.g., 2000–present) for faster MVP?
6. **API rate limiting** — Public API or internal-only?

---

## Timeline (from Site Plan)

| Phase | Duration | Weeks |
|-------|----------|-------|
| Phase 1: Data Foundation | 4–5 weeks | 1–5 |
| Phase 2: API & Search | 4–5 weeks | 5–10 |
| Phase 3: ML Predictions | 4–5 weeks | 10–14 |
| Phase 4: Viz & Polish | 4 weeks | 14–18 |

## Ethical / Legal Notes

- Match results are factual data — OK to store and analyze
- Do NOT reproduce source site presentation/design
- Respect robots.txt on all scraping targets
- Rate limit all scrapers (1 req/sec)
- Cache raw HTML locally to minimize repeat requests
- Attribute data sources on the platform

## Getting Started Checklist

1. [x] Provide `wrestlers_roster_2026.csv`
2. [x] Provide Site Plan document
3. [x] Initialize git repo + push to GitHub
4. [ ] Confirm or update answers to Open Questions above
5. [ ] Begin Phase 1 — `schema.sql` first
