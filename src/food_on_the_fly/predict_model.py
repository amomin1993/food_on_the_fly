"""Batch scoring: run the trained pipeline over a CSV of orders.

    python -m food_on_the_fly.predict_model \
        --model-path models/pipeline.joblib \
        --input data/processed/test.csv \
        --output predictions/test_predictions.csv

The input needs the raw order columns the pipeline was trained on (the same
fields as the API's ``DeliveryRequest``). Extra columns, including the target,
are carried through to the output, so a labelled file can be compared with
its predictions directly.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import pandas as pd

from food_on_the_fly.config import MODELS_DIR, PROCESSED_DATA_DIR
from food_on_the_fly.logging_config import get_logger, setup_logging

logger = get_logger(__name__)

PREDICTION_COL = "predicted_time_min"


def predict(model_path: Path, input_path: Path, output_path: Path) -> pd.DataFrame:
    """Score ``input_path`` with the pipeline at ``model_path``.

    Writes the scored rows to ``output_path`` and returns them.
    """
    logger.info("Loading model from %s", model_path)
    pipeline = joblib.load(model_path)

    logger.info("Scoring %s", input_path)
    frame = pd.read_csv(input_path)
    frame[PREDICTION_COL] = pipeline.predict(frame).round(2)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)
    logger.info("Wrote %d predictions to %s", len(frame), output_path)
    return frame


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint for batch prediction."""
    parser = argparse.ArgumentParser(
        description="Generate predictions from a trained model"
    )
    parser.add_argument(
        "--model-path", type=Path, default=MODELS_DIR / "pipeline.joblib"
    )
    parser.add_argument("--input", type=Path, default=PROCESSED_DATA_DIR / "test.csv")
    parser.add_argument(
        "--output", type=Path, default=Path("predictions/test_predictions.csv")
    )
    args = parser.parse_args(argv)

    setup_logging()
    predict(args.model_path, args.input, args.output)


if __name__ == "__main__":
    main()
