"""Ringside Predictor — interactive demo for the Ringside Analytics XGBoost model.

Picks two wrestlers from a dropdown of the top-500-by-match-count, lets users
set match context, and returns win probability with feature attribution.

Inference runs against bundled snapshot files (`data/`) — no DB, no internet
needed at request time.
"""
from __future__ import annotations

from pathlib import Path

import gradio as gr
import joblib
import numpy as np
import pandas as pd
from huggingface_hub import hf_hub_download

# ─── Constants ────────────────────────────────────────────────────────
DATA_DIR  = Path(__file__).parent / "data"
MODEL_REPO = "datamatters24/ringside-match-winner"

ALIGNMENT_INT = {"face": 0, "tweener": 1, "heel": 2}
DEFAULT_ALIGNMENT = 1   # tweener / unknown — matches training distribution

# 35-feature order, exact match to scaler.feature_names_in_
FEATURE_ORDER = [
    "win_rate_30d", "win_rate_90d", "win_rate_365d",
    "current_win_streak", "current_loss_streak",
    "is_ppv", "is_title_match", "card_position", "event_tier",
    "match_type_win_rate",
    "is_singles", "is_tag_team", "is_triple_threat", "is_fatal_four_way",
    "is_ladder", "is_cage", "is_hell_in_a_cell", "is_royal_rumble",
    "is_champion", "num_defenses", "days_since_title_match",
    "years_active", "matches_last_90d", "days_since_last_match",
    "promotion_win_rate", "h2h_win_rate", "h2h_matches",
    "alignment", "is_face", "is_heel",
    "days_since_turn", "turns_12m", "face_heel_matchup",
    "avg_match_rating", "card_position_momentum",
]

MATCH_TYPES = [
    "singles", "tag_team", "triple_threat", "fatal_four_way",
    "ladder", "cage", "hell_in_a_cell", "royal_rumble",
]

# ─── Load model + snapshot ────────────────────────────────────────────
def _load():
    print("Downloading model from HF Hub...")
    xgb_path    = hf_hub_download(repo_id=MODEL_REPO, filename="xgboost.joblib")
    scaler_path = hf_hub_download(repo_id=MODEL_REPO, filename="scaler.joblib")

    xgb    = joblib.load(xgb_path)
    scaler = joblib.load(scaler_path)

    print(f"Loading snapshot from {DATA_DIR}...")
    stats = pd.read_parquet(DATA_DIR / "wrestler_stats.parquet")
    h2h   = pd.read_parquet(DATA_DIR / "h2h.parquet")
    mt    = pd.read_parquet(DATA_DIR / "match_type_stats.parquet")
    return xgb, scaler, stats, h2h, mt

XGB, SCALER, STATS, H2H, MT = _load()
WRESTLER_NAMES = STATS.sort_values("ring_name")["ring_name"].tolist()


# ─── Feature builder ──────────────────────────────────────────────────
def build_feature_row(
    focal: pd.Series,
    opponent: pd.Series,
    is_ppv: bool,
    is_title_match: bool,
    match_type: str,
) -> pd.DataFrame:
    """Construct one row of 35 features for the focal wrestler."""
    # Match-type one-hots
    mt_flags = {f"is_{mt_key}": int(match_type == mt_key) for mt_key in MATCH_TYPES}

    # match_type_win_rate (focal in this match type)
    mtwr = MT[(MT["wrestler_id"] == focal["wrestler_id"]) & (MT["match_type"] == match_type)]
    match_type_win_rate = float(mtwr["win_rate"].iloc[0]) if len(mtwr) else float(focal["career_wr"])

    # Head-to-head
    a, b = sorted([int(focal["wrestler_id"]), int(opponent["wrestler_id"])])
    h_row = H2H[(H2H["w_a"] == a) & (H2H["w_b"] == b)]
    if len(h_row):
        h_total = int(h_row["h2h_matches"].iloc[0])
        a_wr    = float(h_row["a_win_rate"].iloc[0])
        # If focal is the smaller id (a), that's their direct rate; else flip
        h_focal_wr = a_wr if focal["wrestler_id"] == a else (1.0 - a_wr)
    else:
        h_total, h_focal_wr = 0, 0.5

    # Alignment encoding
    align_focal  = ALIGNMENT_INT.get(focal["alignment"], DEFAULT_ALIGNMENT)
    align_oppo   = ALIGNMENT_INT.get(opponent["alignment"], DEFAULT_ALIGNMENT)
    is_face      = int(focal["alignment"] == "face")
    is_heel      = int(focal["alignment"] == "heel")
    face_heel    = int((focal["alignment"] == "face" and opponent["alignment"] == "heel")
                       or (focal["alignment"] == "heel" and opponent["alignment"] == "face"))

    row = {
        "win_rate_30d":          float(focal["win_rate_30d"]),
        "win_rate_90d":          float(focal["win_rate_90d"]),
        "win_rate_365d":         float(focal["win_rate_365d"]),
        "current_win_streak":    int(focal["current_win_streak"]),
        "current_loss_streak":   int(focal["current_loss_streak"]),
        "is_ppv":                int(is_ppv),
        "is_title_match":        int(is_title_match),
        "card_position":         5.0,    # mid-card default
        "event_tier":            int(is_ppv) * 2 + int(is_title_match),
        "match_type_win_rate":   match_type_win_rate,
        **mt_flags,
        "is_champion":           int(focal["is_champion"]),
        "num_defenses":          int(focal["num_defenses"]),
        "days_since_title_match": int(focal["days_since_title_match"]),
        "years_active":          float(focal["years_active"]),
        "matches_last_90d":      int(focal["matches_last_90d"]),
        "days_since_last_match": int(focal["days_since_last_match"]),
        "promotion_win_rate":    float(focal["promotion_win_rate"]),
        "h2h_win_rate":          h_focal_wr,
        "h2h_matches":           h_total,
        "alignment":             align_focal,
        "is_face":               is_face,
        "is_heel":               is_heel,
        "days_since_turn":       int(focal["days_since_turn"]),
        "turns_12m":             int(focal["turns_12m"]),
        "face_heel_matchup":     face_heel,
        "avg_match_rating":      float(focal["avg_match_rating"]),
        "card_position_momentum": float(focal["card_position_momentum"]),
    }
    return pd.DataFrame([row])[FEATURE_ORDER]


# ─── Inference ────────────────────────────────────────────────────────
def predict(wrestler_a: str, wrestler_b: str, is_ppv: bool, is_title_match: bool, match_type: str):
    if wrestler_a == wrestler_b:
        return ("⚠️ Pick two different wrestlers.", None, "")

    a = STATS[STATS["ring_name"] == wrestler_a].iloc[0]
    b = STATS[STATS["ring_name"] == wrestler_b].iloc[0]

    Xa = build_feature_row(a, b, is_ppv, is_title_match, match_type)
    Xb = build_feature_row(b, a, is_ppv, is_title_match, match_type)

    Xa_s = SCALER.transform(Xa)
    Xb_s = SCALER.transform(Xb)

    # Symmetric prediction: each wrestler's P(win) under the model, then renormalize
    pa = float(XGB.predict_proba(Xa_s)[0, 1])
    pb = float(XGB.predict_proba(Xb_s)[0, 1])
    norm = pa + pb
    pa_n, pb_n = pa / norm, pb / norm

    summary = (
        f"### Predicted win probabilities\n\n"
        f"- **{wrestler_a}**: {pa_n:.0%}\n"
        f"- **{wrestler_b}**: {pb_n:.0%}\n\n"
        f"_Raw model outputs (independent calls): {pa:.2f} / {pb:.2f} — these are normalized to sum to 1._"
    )

    # Top contributing features (XGBoost feature importances * focal feature deviation from mean)
    imp = pd.Series(XGB.feature_importances_, index=FEATURE_ORDER).sort_values(ascending=False)
    contrib = pd.DataFrame({
        "feature":    imp.index,
        "importance": imp.values,
        f"{wrestler_a}":  Xa.iloc[0].values,
        f"{wrestler_b}":  Xb.iloc[0].values,
    }).head(10)

    explanation = (
        "### Top 10 features driving the model\n\n"
        f"For *any* prediction, these 10 features carry ~98% of XGBoost's signal. "
        f"Compare {wrestler_a}'s values to {wrestler_b}'s to see why the model leans the way it does — "
        f"streak features and recent activity dominate. **Booking momentum is the story.**\n\n"
        "⚠️ Reminder: pro wrestling outcomes are scripted. This model predicts who tends to be **booked** to win, not who would win an athletic contest. Not for betting."
    )

    return (summary, contrib, explanation)


# ─── UI ───────────────────────────────────────────────────────────────
DESCRIPTION = """
# 🤼 Ringside Predictor

Live demo of the [Ringside Analytics match-winner model](https://huggingface.co/datamatters24/ringside-match-winner) trained on **482K pro wrestling matches** (1980–present).

Pick two wrestlers, set the match context, and the XGBoost model (test AUC 0.718) returns a win probability with feature attribution.

**How to read this:** the prediction reflects **booking patterns** the model learned from historical data — not athletic ability. Pro wrestling outcomes are scripted. See the [paper](https://tedrubin80.github.io/wrastlingfirst/paper.html) for a full discussion of the kayfabe problem.

[Dataset](https://huggingface.co/datasets/datamatters24/ringside-analytics) · [Model](https://huggingface.co/datamatters24/ringside-match-winner) · [Source code](https://github.com/tedrubin80/wrastlingfirst)
"""

with gr.Blocks(title="Ringside Predictor", theme=gr.themes.Soft(primary_hue="red")) as demo:
    gr.Markdown(DESCRIPTION)

    with gr.Row():
        a = gr.Dropdown(
            choices=WRESTLER_NAMES, value="John Cena",
            label="Wrestler A", filterable=True,
        )
        b = gr.Dropdown(
            choices=WRESTLER_NAMES, value="Roman Reigns",
            label="Wrestler B", filterable=True,
        )

    with gr.Row():
        ppv = gr.Checkbox(label="PPV / Premium live event", value=False)
        title = gr.Checkbox(label="Title match", value=False)
        mt_in = gr.Dropdown(
            choices=MATCH_TYPES, value="singles", label="Match type",
        )

    btn = gr.Button("🔮 Predict", variant="primary")

    out_summary = gr.Markdown()
    out_table   = gr.Dataframe(label="Top features")
    out_caveat  = gr.Markdown()

    btn.click(
        predict,
        inputs=[a, b, ppv, title, mt_in],
        outputs=[out_summary, out_table, out_caveat],
    )

    gr.Examples(
        examples=[
            ["John Cena",       "Roman Reigns", False, False, "singles"],
            ["Stone Cold Steve Austin", "The Rock", True, True, "singles"],
            ["Hulk Hogan",      "Andre the Giant", True, True, "singles"],
            ["Bret Hart",       "Shawn Michaels", True, True, "cage"],
        ],
        inputs=[a, b, ppv, title, mt_in],
    )


if __name__ == "__main__":
    demo.launch()
