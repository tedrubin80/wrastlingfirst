-- ============================================================================
-- Ringside Analytics — PostgreSQL 16 Schema
-- Full DDL for wrestling match history, stats, and ML predictions
-- ============================================================================

BEGIN;

-- ============================================================================
-- ENUM TYPES
-- ============================================================================

CREATE TYPE match_type AS ENUM (
    'singles',
    'tag_team',
    'triple_threat',
    'fatal_four_way',
    'battle_royal',
    'royal_rumble',
    'ladder',
    'tlc',
    'hell_in_a_cell',
    'cage',
    'elimination_chamber',
    'iron_man',
    'i_quit',
    'last_man_standing',
    'tables',
    'handicap',
    'gauntlet',
    'other'
);

CREATE TYPE event_type AS ENUM (
    'ppv',
    'weekly_tv',
    'special',
    'house_show',
    'tournament'
);

CREATE TYPE match_result AS ENUM (
    'win',
    'loss',
    'draw',
    'no_contest',
    'dq',
    'countout'
);

CREATE TYPE wrestler_status AS ENUM (
    'active',
    'inactive',
    'injured',
    'retired',
    'deceased',
    'free_agent'
);

CREATE TYPE gender_type AS ENUM (
    'male',
    'female',
    'other'
);

-- ============================================================================
-- TABLES
-- ============================================================================

-- Promotions: WWE, AEW, WCW, ECW, TNA, NXT, etc.
CREATE TABLE promotions (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    abbreviation    TEXT NOT NULL UNIQUE,
    founded         DATE,
    defunct          DATE,
    parent_org      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE promotions IS 'Wrestling promotions/organizations (WWE, AEW, WCW, etc.)';

-- Wrestlers: master registry of all wrestlers
CREATE TABLE wrestlers (
    id                      SERIAL PRIMARY KEY,
    ring_name               TEXT NOT NULL,
    real_name               TEXT,
    gender                  gender_type NOT NULL DEFAULT 'male',
    birth_date              DATE,
    debut_date              DATE,
    status                  wrestler_status NOT NULL DEFAULT 'active',
    primary_promotion_id    INTEGER REFERENCES promotions(id),
    brand                   TEXT,
    billed_from             TEXT,
    image_url               TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE wrestlers IS 'Master registry of all wrestlers across all promotions and eras';

CREATE INDEX idx_wrestlers_ring_name ON wrestlers (ring_name);
CREATE INDEX idx_wrestlers_status ON wrestlers (status);
CREATE INDEX idx_wrestlers_promotion ON wrestlers (primary_promotion_id);
CREATE INDEX idx_wrestlers_gender ON wrestlers (gender);
CREATE INDEX idx_wrestlers_brand ON wrestlers (brand);

-- Full-text search index on wrestler names
ALTER TABLE wrestlers ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(ring_name, '') || ' ' || coalesce(real_name, ''))
    ) STORED;

CREATE INDEX idx_wrestlers_search ON wrestlers USING GIN (search_vector);

-- Wrestler aliases: maps name variations across eras and promotions
CREATE TABLE wrestler_aliases (
    id              SERIAL PRIMARY KEY,
    wrestler_id     INTEGER NOT NULL REFERENCES wrestlers(id) ON DELETE CASCADE,
    alias           TEXT NOT NULL,
    promotion_id    INTEGER REFERENCES promotions(id),
    active_from     DATE,
    active_to       DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE wrestler_aliases IS 'Name variations across eras/promotions (e.g., "The Rock" / "Rocky Maivia")';

CREATE INDEX idx_aliases_wrestler ON wrestler_aliases (wrestler_id);
CREATE INDEX idx_aliases_alias ON wrestler_aliases (alias);
CREATE UNIQUE INDEX idx_aliases_unique ON wrestler_aliases (wrestler_id, alias, promotion_id)
    WHERE promotion_id IS NOT NULL;

-- Events: PPVs, TV episodes, house shows, specials
CREATE TABLE events (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    promotion_id    INTEGER NOT NULL REFERENCES promotions(id),
    date            DATE NOT NULL,
    venue           TEXT,
    city            TEXT,
    state           TEXT,
    country         TEXT,
    event_type      event_type NOT NULL DEFAULT 'weekly_tv',
    cagematch_id    TEXT UNIQUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE events IS 'Wrestling events — PPVs, weekly TV, house shows, tournaments, specials';

CREATE INDEX idx_events_promotion ON events (promotion_id);
CREATE INDEX idx_events_date ON events (date DESC);
CREATE INDEX idx_events_promotion_date ON events (promotion_id, date DESC);
CREATE INDEX idx_events_type ON events (event_type);
CREATE INDEX idx_events_cagematch ON events (cagematch_id) WHERE cagematch_id IS NOT NULL;

-- Full-text search on event names
ALTER TABLE events ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(name, ''))
    ) STORED;

CREATE INDEX idx_events_search ON events USING GIN (search_vector);

-- Matches: individual matches within events
CREATE TABLE matches (
    id                  SERIAL PRIMARY KEY,
    event_id            INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    match_order         SMALLINT,
    match_type          match_type NOT NULL DEFAULT 'singles',
    stipulation         TEXT,
    duration_seconds    INTEGER,
    title_match         BOOLEAN NOT NULL DEFAULT false,
    rating              DECIMAL(3,2),
    cagematch_id        TEXT UNIQUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_rating_range CHECK (rating IS NULL OR (rating >= 0 AND rating <= 10)),
    CONSTRAINT chk_duration_positive CHECK (duration_seconds IS NULL OR duration_seconds > 0)
);

COMMENT ON TABLE matches IS 'Individual matches — linked to events, typed and rated';

CREATE INDEX idx_matches_event ON matches (event_id);
CREATE INDEX idx_matches_type ON matches (match_type);
CREATE INDEX idx_matches_title ON matches (title_match) WHERE title_match = true;
CREATE INDEX idx_matches_rating ON matches (rating DESC NULLS LAST);

-- Match participants: junction table linking wrestlers to matches with results
CREATE TABLE match_participants (
    id                  SERIAL PRIMARY KEY,
    match_id            INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    wrestler_id         INTEGER NOT NULL REFERENCES wrestlers(id) ON DELETE CASCADE,
    team_number         SMALLINT,
    result              match_result NOT NULL,
    entry_order         SMALLINT,
    elimination_order   SMALLINT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_match_wrestler UNIQUE (match_id, wrestler_id)
);

COMMENT ON TABLE match_participants IS 'Junction table: who was in each match and their result';

CREATE INDEX idx_participants_match ON match_participants (match_id);
CREATE INDEX idx_participants_wrestler ON match_participants (wrestler_id);
CREATE INDEX idx_participants_result ON match_participants (result);
CREATE INDEX idx_participants_wrestler_result ON match_participants (wrestler_id, result);

-- Titles: championship registry
CREATE TABLE titles (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    promotion_id    INTEGER NOT NULL REFERENCES promotions(id),
    established     DATE,
    retired         DATE,
    active          BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_title_name_promotion UNIQUE (name, promotion_id)
);

COMMENT ON TABLE titles IS 'Championship registry — all titles across promotions';

CREATE INDEX idx_titles_promotion ON titles (promotion_id);
CREATE INDEX idx_titles_active ON titles (active) WHERE active = true;

-- Title reigns: historical championship holders
CREATE TABLE title_reigns (
    id                  SERIAL PRIMARY KEY,
    title_id            INTEGER NOT NULL REFERENCES titles(id) ON DELETE CASCADE,
    wrestler_id         INTEGER NOT NULL REFERENCES wrestlers(id) ON DELETE CASCADE,
    won_date            DATE NOT NULL,
    lost_date           DATE,
    defenses            INTEGER NOT NULL DEFAULT 0,
    won_at_event_id     INTEGER REFERENCES events(id),
    lost_at_event_id    INTEGER REFERENCES events(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_reign_dates CHECK (lost_date IS NULL OR lost_date >= won_date),
    CONSTRAINT chk_defenses_positive CHECK (defenses >= 0)
);

COMMENT ON TABLE title_reigns IS 'Championship reign history — who held what and when';

CREATE INDEX idx_reigns_title ON title_reigns (title_id);
CREATE INDEX idx_reigns_wrestler ON title_reigns (wrestler_id);
CREATE INDEX idx_reigns_won_date ON title_reigns (won_date DESC);
CREATE INDEX idx_reigns_current ON title_reigns (title_id, wrestler_id) WHERE lost_date IS NULL;

-- Pre-computed rolling stats for ML feature engineering
CREATE TABLE wrestler_stats_rolling (
    id                  SERIAL PRIMARY KEY,
    wrestler_id         INTEGER NOT NULL REFERENCES wrestlers(id) ON DELETE CASCADE,
    as_of_date          DATE NOT NULL,
    win_rate_30d        DECIMAL(5,4),
    win_rate_90d        DECIMAL(5,4),
    win_rate_365d       DECIMAL(5,4),
    current_win_streak  INTEGER NOT NULL DEFAULT 0,
    current_loss_streak INTEGER NOT NULL DEFAULT 0,
    momentum_score      DECIMAL(6,4),
    push_score          DECIMAL(6,4),
    matches_count_30d   INTEGER NOT NULL DEFAULT 0,
    matches_count_90d   INTEGER NOT NULL DEFAULT 0,
    matches_count_365d  INTEGER NOT NULL DEFAULT 0,
    title_match_rate    DECIMAL(5,4),
    ppv_win_rate        DECIMAL(5,4),
    avg_match_rating    DECIMAL(3,2),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_stats_wrestler_date UNIQUE (wrestler_id, as_of_date)
);

COMMENT ON TABLE wrestler_stats_rolling IS 'Pre-computed rolling stats for ML features — recomputed after each ETL load';

CREATE INDEX idx_stats_wrestler ON wrestler_stats_rolling (wrestler_id);
CREATE INDEX idx_stats_date ON wrestler_stats_rolling (as_of_date DESC);
CREATE INDEX idx_stats_wrestler_date ON wrestler_stats_rolling (wrestler_id, as_of_date DESC);

-- Cached ML prediction results
CREATE TABLE predictions (
    id              SERIAL PRIMARY KEY,
    wrestler_ids    JSONB NOT NULL,
    context         JSONB NOT NULL DEFAULT '{}',
    probabilities   JSONB NOT NULL,
    top_factors     JSONB,
    model_version   TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE predictions IS 'Cached ML prediction results — keyed by wrestler IDs + context for fast lookup';

CREATE INDEX idx_predictions_wrestlers ON predictions USING GIN (wrestler_ids);
CREATE INDEX idx_predictions_created ON predictions (created_at DESC);
CREATE INDEX idx_predictions_model ON predictions (model_version);

-- ============================================================================
-- ALIGNMENT (HEEL / FACE / TWEENER) TRACKING
-- ============================================================================

CREATE TYPE alignment_type AS ENUM ('face', 'heel', 'tweener');

-- Current and historical alignment snapshots per wrestler
CREATE TABLE wrestler_alignments (
    id              SERIAL PRIMARY KEY,
    wrestler_id     INTEGER NOT NULL REFERENCES wrestlers(id) ON DELETE CASCADE,
    alignment       alignment_type NOT NULL,
    effective_date  DATE NOT NULL,
    source          TEXT,  -- e.g. 'smackdown_hotel', 'smark_out_moment', 'manual'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_alignment_wrestler_date UNIQUE (wrestler_id, effective_date)
);

COMMENT ON TABLE wrestler_alignments IS 'Point-in-time alignment snapshots — face/heel/tweener per wrestler';

CREATE INDEX idx_alignments_wrestler ON wrestler_alignments (wrestler_id);
CREATE INDEX idx_alignments_date ON wrestler_alignments (effective_date DESC);
CREATE INDEX idx_alignments_wrestler_date ON wrestler_alignments (wrestler_id, effective_date DESC);

-- Alignment turn events (face→heel, heel→face, etc.)
CREATE TABLE alignment_turns (
    id              SERIAL PRIMARY KEY,
    wrestler_id     INTEGER NOT NULL REFERENCES wrestlers(id) ON DELETE CASCADE,
    from_alignment  alignment_type NOT NULL,
    to_alignment    alignment_type NOT NULL,
    turn_date       DATE NOT NULL,
    event_id        INTEGER REFERENCES events(id),
    description     TEXT,
    source          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_turn_different CHECK (from_alignment <> to_alignment)
);

COMMENT ON TABLE alignment_turns IS 'Heel/face turn events with date, context, and source attribution';

CREATE INDEX idx_turns_wrestler ON alignment_turns (wrestler_id);
CREATE INDEX idx_turns_date ON alignment_turns (turn_date DESC);
CREATE INDEX idx_turns_wrestler_date ON alignment_turns (wrestler_id, turn_date DESC);

-- ============================================================================
-- UPDATED_AT TRIGGER
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_promotions_updated_at
    BEFORE UPDATE ON promotions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_wrestlers_updated_at
    BEFORE UPDATE ON wrestlers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_events_updated_at
    BEFORE UPDATE ON events
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_matches_updated_at
    BEFORE UPDATE ON matches
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_titles_updated_at
    BEFORE UPDATE ON titles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_title_reigns_updated_at
    BEFORE UPDATE ON title_reigns
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

COMMIT;
