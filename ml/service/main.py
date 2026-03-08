"""
FastAPI prediction service — accepts wrestler IDs and context,
returns win probabilities with explainable factors.
"""

import os

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from service.predict import PredictionEngine

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="Ringside Analytics — Prediction Service",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000")],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# Initialize prediction engine on startup
engine = PredictionEngine()


class PredictionRequest(BaseModel):
    wrestler_ids: list[int] = Field(..., min_length=2, max_length=8)
    match_type: str = "singles"
    event_tier: str = "weekly_tv"
    title_match: bool = False


class ProbabilityResult(BaseModel):
    wrestler_id: int
    win_probability: float
    confidence: float


class FactorResult(BaseModel):
    feature: str
    label: str
    difference: float
    favored_value: float


class PredictionResponse(BaseModel):
    probabilities: list[ProbabilityResult]
    factors: list[FactorResult]
    model_version: str
    message: str | None = None


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model_loaded": engine.model is not None,
        "model_version": engine.model_version,
    }


@app.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest):
    """
    Predict match outcome probabilities for a set of wrestlers.

    Returns win probability for each wrestler, confidence score,
    and top contributing factors with human-readable labels.
    """
    try:
        result = engine.predict(
            wrestler_ids=request.wrestler_ids,
            match_type=request.match_type,
            event_tier=request.event_tier,
            title_match=request.title_match,
        )
        return PredictionResponse(**result)

    except Exception as e:
        logger.exception("prediction_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("ML_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
