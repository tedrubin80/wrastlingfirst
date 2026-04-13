#!/usr/bin/env bash
# Nightly data refresh — runs at 3 AM EST via cron
# Steps: scrape recent data → ETL load → recompute stats → invalidate cache
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="${PROJECT_DIR}/logs"
SCRAPE_DIR="${PROJECT_DIR}/data/scraped"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${LOG_DIR}/nightly_${TIMESTAMP}.log"

mkdir -p "$LOG_DIR" "$SCRAPE_DIR"

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $1" | tee -a "$LOG_FILE"
}

log "=== Nightly refresh started ==="

# 1. Scrape recent matches (last 7 days) for all active promotions
log "Step 1: Scraping recent matches..."
CURRENT_YEAR=$(date +%Y)
python3 -m scraper --output-dir "$SCRAPE_DIR" \
  --year-start "$CURRENT_YEAR" --year-end "$CURRENT_YEAR" \
  --promotions WWE AEW 2>&1 | tee -a "$LOG_FILE" || {
  log "WARNING: Scraper encountered errors (continuing with available data)"
}

# 2. ETL load
log "Step 2: Loading scraped data into database..."
python3 -m etl --input-dir "$SCRAPE_DIR" 2>&1 | tee -a "$LOG_FILE" || {
  log "ERROR: ETL load failed"
  exit 1
}

# 3. Recompute rolling stats
log "Step 3: Recomputing rolling stats..."
python3 -m etl --stats-only 2>&1 | tee -a "$LOG_FILE" || {
  log "ERROR: Stats recomputation failed"
  exit 1
}

# 4. Invalidate Redis cache
log "Step 4: Invalidating Redis cache..."
if command -v redis-cli &>/dev/null; then
  REDIS_URL="${REDIS_URL:-redis://localhost:6379}"
  redis-cli -u "$REDIS_URL" FLUSHDB 2>&1 | tee -a "$LOG_FILE" || {
    log "WARNING: Cache invalidation failed (non-critical)"
  }
else
  log "WARNING: redis-cli not available, skipping cache invalidation"
fi

# 5. Check if it's Sunday — retrain ML model weekly
DOW=$(date +%u)
if [ "$DOW" -eq 7 ]; then
  log "Step 5: Sunday — retraining ML model..."
  cd "$PROJECT_DIR/ml" && python3 -m train 2>&1 | tee -a "$LOG_FILE" || {
    log "WARNING: Model retraining failed (continuing with existing model)"
  }
else
  log "Step 5: Skipping model retrain (not Sunday)"
fi

log "=== Nightly refresh completed ==="
