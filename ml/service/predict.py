"""
Real-time prediction logic — compute features and run inference.
"""

import hashlib
import json
import os
from datetime import date, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import psycopg2
import redis
import structlog

logger = structlog.get_logger(__name__)

MODEL_DIR = Path(__file__).parent.parent / "models"
DB_URL = os.environ.get("DATABASE_URL", "postgresql://ringside:ringside@localhost:5432/ringside")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

# Feature names must match training
FEATURE_COLUMNS = [
    # Win momentum (5)
    "win_rate_30d", "win_rate_90d", "win_rate_365d",
    "current_win_streak", "current_loss_streak",
    # Event context (4)
    "is_ppv", "is_title_match", "card_position", "event_tier",
    # Match type (9)
    "match_type_win_rate",
    "is_singles", "is_tag_team", "is_triple_threat", "is_fatal_four_way",
    "is_ladder", "is_cage", "is_hell_in_a_cell", "is_royal_rumble",
    # Title proximity (3)
    "is_champion", "num_defenses", "days_since_title_match",
    # Career phase (3)
    "years_active", "matches_last_90d", "days_since_last_match",
    # Promotion (1)
    "promotion_win_rate",
    # Head-to-head (2)
    "h2h_win_rate", "h2h_matches",
    # Alignment (6)
    "alignment", "is_face", "is_heel",
    "days_since_turn", "turns_12m", "face_heel_matchup",
    # Match quality (1)
    "avg_match_rating",
    # Card position momentum (1)
    "card_position_momentum",
]

# Human-readable factor explanations
FACTOR_LABELS = {
    "win_rate_30d": "Recent win rate (last 30 days)",
    "win_rate_90d": "Win rate over last 3 months",
    "win_rate_365d": "Annual win rate",
    "current_win_streak": "Current winning streak",
    "current_loss_streak": "Current losing streak",
    "is_ppv": "PPV match (higher stakes)",
    "is_title_match": "Championship on the line",
    "card_position": "Position on the card (main event = higher)",
    "event_tier": "Event importance level",
    "match_type_win_rate": "Win rate in this match type",
    "is_champion": "Currently holds a championship",
    "num_defenses": "Number of title defenses",
    "days_since_title_match": "Days since last title match",
    "years_active": "Years of career experience",
    "matches_last_90d": "Recent activity level (matches in 90 days)",
    "days_since_last_match": "Days since last match",
    "promotion_win_rate": "Win rate in this promotion",
    "h2h_win_rate": "Head-to-head record vs opponent",
    "h2h_matches": "Number of prior meetings",
    "alignment": "Current alignment (face/tweener/heel)",
    "is_face": "Wrestling as a face (fan favorite)",
    "is_heel": "Wrestling as a heel (villain)",
    "days_since_turn": "Days since last alignment turn",
    "turns_12m": "Alignment turns in last 12 months",
    "face_heel_matchup": "Classic face vs heel matchup",
    "avg_match_rating": "Average match quality rating",
    "card_position_momentum": "Card position trend (push trajectory)",
}


class PredictionEngine:
    """Loads trained models and computes predictions."""

    def __init__(self):
        self.model = None
        self.scaler = None
        self.model_version = "unknown"
        self._redis = None
        self._load_model()
        self._connect_redis()

    def _load_model(self) -> None:
        """Load the best available model."""
        xgb_path = MODEL_DIR / "xgboost.joblib"
        lr_path = MODEL_DIR / "logistic_regression.joblib"
        scaler_path = MODEL_DIR / "scaler.joblib"

        if xgb_path.exists():
            self.model = joblib.load(xgb_path)
            self.model_version = "xgboost-v1"
            logger.info("model_loaded", model="xgboost")
        elif lr_path.exists():
            self.model = joblib.load(lr_path)
            if scaler_path.exists():
                self.scaler = joblib.load(scaler_path)
            self.model_version = "logistic-regression-v1"
            logger.info("model_loaded", model="logistic_regression")
        else:
            logger.warning("no_model_found", path=str(MODEL_DIR))

    def _connect_redis(self) -> None:
        try:
            self._redis = redis.from_url(REDIS_URL)
            self._redis.ping()
        except Exception:
            self._redis = None
            logger.warning("redis_unavailable")

    def _cache_key(self, wrestler_ids: list[int], context: dict) -> str:
        """Build a deterministic cache key."""
        key_data = json.dumps({
            "ids": sorted(wrestler_ids),
            "ctx": context,
        }, sort_keys=True)
        return f"pred:{hashlib.sha256(key_data.encode()).hexdigest()[:16]}"

    def _get_cached(self, key: str) -> dict | None:
        if not self._redis:
            return None
        try:
            data = self._redis.get(key)
            return json.loads(data) if data else None
        except Exception:
            return None

    def _set_cached(self, key: str, data: dict, ttl: int = 3600) -> None:
        if not self._redis:
            return
        try:
            self._redis.setex(key, ttl, json.dumps(data))
        except Exception:
            pass

    def compute_live_features(
        self,
        wrestler_id: int,
        match_type: str = "singles",
        event_tier: str = "weekly_tv",
        title_match: bool = False,
        opponent_id: int | None = None,
    ) -> dict:
        """Compute features for a wrestler in real-time from the database."""
        conn = psycopg2.connect(DB_URL)
        try:
            with conn.cursor() as cur:
                today = date.today()

                # Get rolling stats (pre-computed)
                cur.execute(
                    """SELECT win_rate_30d, win_rate_90d, win_rate_365d,
                              current_win_streak, current_loss_streak,
                              matches_count_90d, title_match_rate, ppv_win_rate
                     FROM wrestler_stats_rolling
                     WHERE wrestler_id = %s
                     ORDER BY as_of_date DESC LIMIT 1""",
                    (wrestler_id,)
                )
                stats_row = cur.fetchone()

                if stats_row:
                    win_rate_30d, win_rate_90d, win_rate_365d = (
                        float(stats_row[0] or 0),
                        float(stats_row[1] or 0),
                        float(stats_row[2] or 0),
                    )
                    win_streak = int(stats_row[3] or 0)
                    loss_streak = int(stats_row[4] or 0)
                    matches_90d = int(stats_row[5] or 0)
                else:
                    win_rate_30d = win_rate_90d = win_rate_365d = 0.5
                    win_streak = loss_streak = 0
                    matches_90d = 0

                # Is champion?
                cur.execute(
                    """SELECT count(*), coalesce(sum(defenses), 0)
                     FROM title_reigns
                     WHERE wrestler_id = %s AND lost_date IS NULL""",
                    (wrestler_id,)
                )
                champ_row = cur.fetchone()
                is_champion = int((champ_row[0] or 0) > 0)
                num_defenses = int(champ_row[1] or 0)

                # Days since last title match
                cur.execute(
                    """SELECT max(e.date)
                     FROM match_participants mp
                     JOIN matches m ON m.id = mp.match_id
                     JOIN events e ON e.id = m.event_id
                     WHERE mp.wrestler_id = %s AND m.title_match = true""",
                    (wrestler_id,)
                )
                last_title = cur.fetchone()[0]
                days_since_title = (today - last_title).days if last_title else 999

                # Years active
                cur.execute(
                    """SELECT min(e.date)
                     FROM match_participants mp
                     JOIN events e ON e.id = (SELECT event_id FROM matches WHERE id = mp.match_id)
                     WHERE mp.wrestler_id = %s""",
                    (wrestler_id,)
                )
                first_match = cur.fetchone()[0]
                years_active = (today - first_match).days / 365.25 if first_match else 0

                # Days since last match
                cur.execute(
                    """SELECT max(e.date)
                     FROM match_participants mp
                     JOIN matches m ON m.id = mp.match_id
                     JOIN events e ON e.id = m.event_id
                     WHERE mp.wrestler_id = %s""",
                    (wrestler_id,)
                )
                last_match = cur.fetchone()[0]
                days_since_last = (today - last_match).days if last_match else 30

                # Match type win rate
                cur.execute(
                    """SELECT count(*) FILTER (WHERE mp.result = 'win'),
                              count(*)
                     FROM match_participants mp
                     JOIN matches m ON m.id = mp.match_id
                     WHERE mp.wrestler_id = %s AND m.match_type = %s::match_type""",
                    (wrestler_id, match_type)
                )
                mt_row = cur.fetchone()
                mt_wins = int(mt_row[0] or 0)
                mt_total = int(mt_row[1] or 0)
                mt_win_rate = mt_wins / mt_total if mt_total > 0 else 0.5

                # H2H vs opponent
                h2h_win_rate = 0.5
                h2h_matches = 0
                if opponent_id:
                    cur.execute(
                        """SELECT
                              count(*) FILTER (WHERE mp1.result = 'win'),
                              count(*)
                         FROM match_participants mp1
                         JOIN match_participants mp2 ON mp2.match_id = mp1.match_id
                           AND mp2.wrestler_id = %s
                         WHERE mp1.wrestler_id = %s""",
                        (opponent_id, wrestler_id)
                    )
                    h2h_row = cur.fetchone()
                    h2h_wins = int(h2h_row[0] or 0)
                    h2h_matches = int(h2h_row[1] or 0)
                    h2h_win_rate = h2h_wins / h2h_matches if h2h_matches > 0 else 0.5

                # Event tier mapping
                tier_map = {"ppv": 3, "special": 2, "weekly_tv": 1}
                event_tier_num = tier_map.get(event_tier, 1)

                # Match type flags
                match_type_flags = {f"is_{mt}": int(match_type == mt) for mt in [
                    "singles", "tag_team", "triple_threat", "fatal_four_way",
                    "ladder", "cage", "hell_in_a_cell", "royal_rumble"
                ]}

        finally:
            conn.close()

        return {
            "win_rate_30d": win_rate_30d,
            "win_rate_90d": win_rate_90d,
            "win_rate_365d": win_rate_365d,
            "current_win_streak": win_streak,
            "current_loss_streak": loss_streak,
            "is_ppv": int(event_tier == "ppv"),
            "is_title_match": int(title_match),
            "card_position": 0.8 if event_tier == "ppv" else 0.5,
            "event_tier": event_tier_num,
            "match_type_win_rate": mt_win_rate,
            **match_type_flags,
            "is_champion": is_champion,
            "num_defenses": num_defenses,
            "days_since_title_match": days_since_title,
            "years_active": years_active,
            "matches_last_90d": matches_90d,
            "days_since_last_match": days_since_last,
            "promotion_win_rate": win_rate_365d,  # Approximate
            "h2h_win_rate": h2h_win_rate,
            "h2h_matches": h2h_matches,
        }

    def predict(
        self,
        wrestler_ids: list[int],
        match_type: str = "singles",
        event_tier: str = "weekly_tv",
        title_match: bool = False,
    ) -> dict:
        """Run a prediction for a set of wrestlers."""
        context = {
            "match_type": match_type,
            "event_tier": event_tier,
            "title_match": title_match,
        }

        # Check cache
        cache_key = self._cache_key(wrestler_ids, context)
        cached = self._get_cached(cache_key)
        if cached:
            logger.info("prediction_cache_hit", key=cache_key)
            return cached

        if self.model is None:
            # No model trained — return equal probabilities
            n = len(wrestler_ids)
            return {
                "probabilities": [
                    {"wrestler_id": wid, "win_probability": round(1 / n, 4), "confidence": 0.0}
                    for wid in wrestler_ids
                ],
                "factors": [],
                "model_version": "no-model",
                "message": "No trained model available. Run ml/train.py first.",
            }

        # Compute features for each wrestler
        feature_rows = []
        for i, wid in enumerate(wrestler_ids):
            # For H2H, use first opponent (simplification for multi-person matches)
            opponent_id = wrestler_ids[1 - i] if len(wrestler_ids) == 2 else None
            features = self.compute_live_features(
                wid, match_type, event_tier, title_match, opponent_id
            )
            feature_rows.append(features)

        # Build feature matrix
        X = pd.DataFrame(feature_rows)[FEATURE_COLUMNS]

        # Scale if using logistic regression
        if self.scaler is not None:
            X_input = self.scaler.transform(X)
        else:
            X_input = X

        # Predict probabilities
        raw_probs = self.model.predict_proba(X_input)[:, 1]

        # Normalize probabilities to sum to 1
        prob_sum = raw_probs.sum()
        if prob_sum > 0:
            normalized = raw_probs / prob_sum
        else:
            normalized = np.ones(len(wrestler_ids)) / len(wrestler_ids)

        # Confidence: how far from uniform distribution
        uniform = 1.0 / len(wrestler_ids)
        confidence = float(np.max(np.abs(normalized - uniform)) / uniform)

        # Top contributing factors
        factors = self._explain_prediction(feature_rows, normalized)

        result = {
            "probabilities": [
                {
                    "wrestler_id": wid,
                    "win_probability": round(float(prob), 4),
                    "confidence": round(confidence, 4),
                }
                for wid, prob in zip(wrestler_ids, normalized)
            ],
            "factors": factors,
            "model_version": self.model_version,
        }

        # Cache result
        self._set_cached(cache_key, result)

        return result

    def _explain_prediction(
        self, feature_rows: list[dict], probabilities: np.ndarray
    ) -> list[dict]:
        """Extract top contributing factors with human-readable explanations."""
        if len(feature_rows) < 2:
            return []

        # Compare features between highest and lowest probability wrestlers
        best_idx = int(np.argmax(probabilities))
        worst_idx = int(np.argmin(probabilities))

        best_features = feature_rows[best_idx]
        worst_features = feature_rows[worst_idx]

        diffs = []
        for col in FEATURE_COLUMNS:
            diff = best_features.get(col, 0) - worst_features.get(col, 0)
            if abs(diff) > 0.01:
                diffs.append({
                    "feature": col,
                    "label": FACTOR_LABELS.get(col, col),
                    "difference": round(diff, 3),
                    "favored_value": round(best_features.get(col, 0), 3),
                })

        # Sort by absolute difference
        diffs.sort(key=lambda x: abs(x["difference"]), reverse=True)
        return diffs[:5]
