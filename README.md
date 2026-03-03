# Ringside Analytics

Data-driven wrestling analytics platform — match history, career stats, and ML-powered match outcome predictions covering 40+ years of professional wrestling.

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for local development)

### 1. Start Infrastructure

```bash
docker compose up -d db redis
```

This starts PostgreSQL 16 and Redis 7. The schema is auto-applied on first run via `schema.sql`.

### 2. Seed Wrestler Data

```bash
docker compose run --rm seed
```

Loads `wrestlers_roster_2026.csv` (354 wrestlers) into the `promotions` and `wrestlers` tables.

### 3. Run the Scraper

```bash
# Scrape WWE + AEW data for 2020-2026
docker compose run --rm scraper

# Or run locally with options
python -m scraper --promotions WWE AEW --year-start 2000 --year-end 2026
```

Scraped data is cached locally and output as JSON in `./output/`.

### 4. Run the ETL Pipeline

```bash
# Load scraped JSON into the database
docker compose run --rm etl

# Or run locally
python -m etl --input-dir ./output
```

After loading, rolling stats are automatically recomputed for all affected wrestlers.

## Project Structure

```
├── schema.sql              # PostgreSQL DDL (10 tables, ENUMs, indexes)
├── seed.py                 # CSV → database loader
├── docker-compose.yml      # PostgreSQL 16, Redis 7, job containers
├── Dockerfile.python       # Python 3.11 image for scraper/ETL
├── requirements.txt        # Python dependencies
├── scraper/                # Cagematch.net scraper
│   ├── cagematch.py        #   Main scraper orchestrator
│   ├── parser.py           #   HTML parsing and data extraction
│   ├── http_client.py      #   Rate-limited HTTP client with caching
│   ├── config.py           #   Scraper configuration
│   └── cli.py              #   CLI entry point
├── etl/                    # Extract-Transform-Load pipeline
│   ├── load.py             #   Database loader with upserts
│   ├── entity_resolution.py#   Fuzzy wrestler name matching
│   ├── stats.py            #   Rolling stats computation
│   └── cli.py              #   CLI entry point
├── wrestlers_roster_2026.csv
├── PLAN.md                 # Full engineering plan (4 phases)
└── .env.example            # Environment variable template
```

## Database

PostgreSQL 16 with 10 tables:

| Table | Description |
|-------|-------------|
| `promotions` | WWE, AEW, WCW, ECW, TNA, NXT |
| `wrestlers` | Master registry with full-text search |
| `wrestler_aliases` | Name variations for entity resolution |
| `events` | PPVs, TV episodes, house shows |
| `matches` | Match details with type, duration, rating |
| `match_participants` | Who was in each match and their result |
| `titles` | Championship registry |
| `title_reigns` | Championship reign history |
| `wrestler_stats_rolling` | Pre-computed ML features |
| `predictions` | Cached ML prediction results |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://ringside:ringside@localhost:5432/ringside` | PostgreSQL connection |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection |
| `SCRAPER_RATE_LIMIT` | `1.0` | Seconds between HTTP requests |
| `SCRAPER_CACHE_DIR` | `./cache` | Local HTML cache directory |

## Scraper Usage

```bash
python -m scraper \
  --promotions WWE AEW WCW ECW TNA NXT \
  --year-start 1980 \
  --year-end 2026 \
  --rate-limit 1.0 \
  --output-dir ./output \
  --cache-dir ./cache
```

## ETL Usage

```bash
# Load all JSON files from output directory
python -m etl --input-dir ./output

# Load a single file
python -m etl --file ./output/wwe_2024.json

# Recompute stats only (no data load)
python -m etl --stats-only
```

## Roadmap

See [PLAN.md](PLAN.md) for the full 4-phase engineering plan:

1. **Data Foundation** (current) — Schema, scraper, ETL, Docker
2. **API & Search** — Express REST API, Next.js frontend
3. **ML Predictions** — XGBoost model, FastAPI service
4. **Visualizations** — Recharts components, nightly refresh, monitoring
