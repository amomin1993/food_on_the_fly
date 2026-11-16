"""Evaluation plots for the delivery-time regressor.

Used by ``train_model.py`` to produce the CML report images. Every function
writes a PNG and closes its figure, so they are safe to call on a headless
runner.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def plot_prediction_scatter(y_true: Any, y_pred: Any, path: str | Path) -> None:
    """Predicted vs actual delivery time, with the perfect-prediction line."""
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    plt.figure(figsize=(10, 6))
    plt.scatter(y_true, y_pred, alpha=0.5, s=10)
    lo, hi = y_true.min(), y_true.max()
    plt.plot([lo, hi], [lo, hi], "r--", lw=2, label="Perfect Prediction")
    plt.xlabel("Actual Delivery Time (min)", fontsize=12)
    plt.ylabel("Predicted Delivery Time (min)", fontsize=12)
    plt.title("Prediction vs Actual Delivery Time", fontsize=14)
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(path, dpi=100, bbox_inches="tight")
    plt.close()


def plot_residuals(y_true: Any, y_pred: Any, path: str | Path) -> None:
    """Residuals against predictions; a flat band around zero is what we want."""
    y_pred = np.asarray(y_pred)
    residuals = np.asarray(y_true) - y_pred
    plt.figure(figsize=(10, 6))
    plt.scatter(y_pred, residuals, alpha=0.5, s=10)
    plt.axhline(y=0, color="r", linestyle="--", lw=2)
    plt.xlabel("Predicted Delivery Time (min)", fontsize=12)
    plt.ylabel("Residuals (Actual - Predicted)", fontsize=12)
    plt.title("Residual Plot - Are Errors Random?", fontsize=14)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(path, dpi=100, bbox_inches="tight")
    plt.close()


def plot_error_distribution(y_true: Any, y_pred: Any, path: str | Path) -> None:
    """Histogram of prediction errors in minutes."""
    residuals = np.asarray(y_true) - np.asarray(y_pred)
    plt.figure(figsize=(10, 6))
    plt.hist(residuals, bins=50, edgecolor="black", alpha=0.7)
    plt.xlabel("Prediction Error (minutes)", fontsize=12)
    plt.ylabel("Frequency", fontsize=12)
    plt.title("Distribution of Prediction Errors", fontsize=14)
    plt.axvline(x=0, color="r", linestyle="--", lw=2, label="Zero Error")
    plt.legend()
    plt.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()
    plt.savefig(path, dpi=100, bbox_inches="tight")
    plt.close()


def top_feature_importances(pipeline: Any, top_n: int = 15) -> list[tuple[str, float]]:
    """XGBoost split counts mapped back to readable feature names, largest first."""
    booster = pipeline.named_steps["regressor"].get_booster()
    scores = booster.get_score(importance_type="weight")
    try:
        names = list(pipeline.named_steps["preprocessor"].get_feature_names_out())
    except AttributeError:
        names = [f"f{i}" for i in range(len(scores))]

    named: dict[str, float] = {}
    for key, value in scores.items():
        idx = int(key[1:])  # XGBoost names columns f0, f1, ...
        if idx < len(names):
            named[names[idx].split("__", 1)[-1]] = float(value)
    return sorted(named.items(), key=lambda kv: kv[1], reverse=True)[:top_n]


def plot_feature_importance(
    pipeline: Any, path: str | Path, top_n: int = 15
) -> list[str]:
    """Bar chart of the top features; returns their names, most important first."""
    ranked = top_feature_importances(pipeline, top_n)
    if not ranked:
        return []
    features = [name for name, _ in ranked]
    values = [value for _, value in ranked]
    plt.figure(figsize=(10, 8))
    plt.barh(range(len(features)), values)
    plt.yticks(range(len(features)), features, fontsize=10)
    plt.xlabel("Importance (Weight)", fontsize=12)
    plt.ylabel("Feature", fontsize=12)
    plt.title(f"Top {top_n} Feature Importances", fontsize=14)
    plt.tight_layout()
    plt.savefig(path, dpi=100, bbox_inches="tight")
    plt.close()
    return features
