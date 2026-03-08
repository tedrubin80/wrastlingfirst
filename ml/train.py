"""
Model training pipeline for match outcome prediction.

Temporal train/test split:
  - Train: matches before 2024
  - Validate: 2024 matches
  - Test: 2025+ matches

Models: Logistic Regression (baseline), XGBoost (primary)
"""

import os
import json
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import structlog
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    roc_auc_score,
    log_loss,
    classification_report,
)
from sklearn.calibration import calibration_curve
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from features import build_feature_matrix, FEATURE_COLUMNS

logger = structlog.get_logger(__name__)

MODEL_DIR = Path(__file__).parent / "models"
MODEL_DIR.mkdir(exist_ok=True)

# MLflow tracking (optional — runs without it)
try:
    import mlflow
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False


def temporal_split(
    df: pd.DataFrame,
    val_year: int = 2024,
    test_year: int = 2025,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split data temporally — no future leakage."""
    train = df[df["event_date"].dt.year < val_year]
    val = df[(df["event_date"].dt.year >= val_year) & (df["event_date"].dt.year < test_year)]
    test = df[df["event_date"].dt.year >= test_year]

    logger.info(
        "data_split",
        train=len(train),
        val=len(val),
        test=len(test),
    )
    return train, val, test


def evaluate_model(
    name: str,
    model,
    X: pd.DataFrame,
    y: pd.Series,
    split_name: str,
) -> dict:
    """Evaluate a model and return metrics."""
    y_pred = model.predict(X)
    y_prob = model.predict_proba(X)[:, 1]

    accuracy = accuracy_score(y, y_pred)
    auc = roc_auc_score(y, y_prob)
    logloss = log_loss(y, y_prob)

    metrics = {
        "model": name,
        "split": split_name,
        "accuracy": round(accuracy, 4),
        "auc_roc": round(auc, 4),
        "log_loss": round(logloss, 4),
    }

    logger.info("evaluation", **metrics)
    return metrics


def get_feature_importance(model, feature_names: list[str]) -> list[dict]:
    """Extract and rank feature importance from the model."""
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
    elif hasattr(model, "coef_"):
        importances = np.abs(model.coef_[0])
    else:
        return []

    ranked = sorted(
        zip(feature_names, importances),
        key=lambda x: x[1],
        reverse=True,
    )

    return [
        {"feature": name, "importance": round(float(imp), 4)}
        for name, imp in ranked
    ]


def train_models(features_df: pd.DataFrame) -> dict:
    """Train baseline and primary models, evaluate, and save."""
    train_df, val_df, test_df = temporal_split(features_df)

    if len(train_df) == 0:
        logger.error("no_training_data")
        return {"error": "No training data available"}

    X_train = train_df[FEATURE_COLUMNS]
    y_train = train_df["won"]
    X_val = val_df[FEATURE_COLUMNS] if len(val_df) > 0 else X_train
    y_val = val_df["won"] if len(val_df) > 0 else y_train
    X_test = test_df[FEATURE_COLUMNS] if len(test_df) > 0 else X_val
    y_test = test_df["won"] if len(test_df) > 0 else y_val

    results = {"models": [], "timestamp": datetime.utcnow().isoformat()}

    # === Start MLflow run ===
    if MLFLOW_AVAILABLE:
        mlflow.set_experiment("ringside-predictions")

    # === Baseline: Logistic Regression ===
    logger.info("training_logistic_regression")
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)
    X_test_scaled = scaler.transform(X_test)

    lr_model = LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
        C=1.0,
        random_state=42,
    )
    lr_model.fit(X_train_scaled, y_train)

    lr_val_metrics = evaluate_model(
        "logistic_regression", lr_model, X_val_scaled, y_val, "validation"
    )
    lr_test_metrics = evaluate_model(
        "logistic_regression", lr_model, X_test_scaled, y_test, "test"
    )

    lr_importance = get_feature_importance(lr_model, FEATURE_COLUMNS)
    results["models"].append({
        "name": "logistic_regression",
        "validation": lr_val_metrics,
        "test": lr_test_metrics,
        "feature_importance": lr_importance[:10],
    })

    # Save LR model + scaler
    joblib.dump(lr_model, MODEL_DIR / "logistic_regression.joblib")
    joblib.dump(scaler, MODEL_DIR / "scaler.joblib")

    # === Primary: XGBoost ===
    logger.info("training_xgboost")
    xgb_model = XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        reg_alpha=0.1,
        reg_lambda=1.0,
        scale_pos_weight=1.0,
        use_label_encoder=False,
        eval_metric="logloss",
        random_state=42,
        early_stopping_rounds=20,
    )

    xgb_model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )

    xgb_val_metrics = evaluate_model(
        "xgboost", xgb_model, X_val, y_val, "validation"
    )
    xgb_test_metrics = evaluate_model(
        "xgboost", xgb_model, X_test, y_test, "test"
    )

    xgb_importance = get_feature_importance(xgb_model, FEATURE_COLUMNS)
    results["models"].append({
        "name": "xgboost",
        "validation": xgb_val_metrics,
        "test": xgb_test_metrics,
        "feature_importance": xgb_importance[:10],
    })

    # Save XGBoost model
    joblib.dump(xgb_model, MODEL_DIR / "xgboost.joblib")

    # === Log to MLflow ===
    if MLFLOW_AVAILABLE:
        with mlflow.start_run(run_name="xgboost-primary"):
            mlflow.log_params({
                "n_estimators": 300,
                "max_depth": 6,
                "learning_rate": 0.1,
                "train_size": len(X_train),
                "val_size": len(X_val),
                "test_size": len(X_test),
                "n_features": len(FEATURE_COLUMNS),
            })
            mlflow.log_metrics(xgb_test_metrics)
            mlflow.sklearn.log_model(xgb_model, "model")

    # === Model comparison ===
    best_model = max(results["models"], key=lambda m: m["test"]["accuracy"])
    results["best_model"] = best_model["name"]
    results["best_accuracy"] = best_model["test"]["accuracy"]
    results["best_auc"] = best_model["test"]["auc_roc"]

    # Save results report
    report_path = MODEL_DIR / "training_report.json"
    report_path.write_text(json.dumps(results, indent=2))
    logger.info("training_complete", best_model=results["best_model"],
                accuracy=results["best_accuracy"], auc=results["best_auc"])

    # Print summary
    print("\n" + "=" * 60)
    print("MODEL TRAINING REPORT")
    print("=" * 60)
    for model_result in results["models"]:
        print(f"\n{model_result['name'].upper()}")
        print(f"  Validation: acc={model_result['validation']['accuracy']}, "
              f"AUC={model_result['validation']['auc_roc']}")
        print(f"  Test:       acc={model_result['test']['accuracy']}, "
              f"AUC={model_result['test']['auc_roc']}")
        print(f"  Top features:")
        for f in model_result["feature_importance"][:5]:
            print(f"    - {f['feature']}: {f['importance']}")

    print(f"\nBest model: {results['best_model']} "
          f"(accuracy: {results['best_accuracy']}, AUC: {results['best_auc']})")
    print(f"\nModels saved to {MODEL_DIR}/")

    return results


def main():
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )

    logger.info("starting_training_pipeline")
    features_df = build_feature_matrix()

    if len(features_df) == 0:
        print("No match data available for training. Run the scraper and ETL first.")
        return

    results = train_models(features_df)
    return results


if __name__ == "__main__":
    main()
