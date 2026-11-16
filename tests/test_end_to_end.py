"""End-to-end run of the training workflow on a small synthetic dataset.

Runs the same entry points CI and Vertex AI run, in order:
temporal split -> train -> evaluate -> batch predict. Everything is written
under ``tmp_path`` so the real data, models and MLflow store are untouched,
and no network or real dataset is needed.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import joblib
import mlflow
import numpy as np
import pandas as pd
import pytest
from hydra import compose, initialize_config_dir
from omegaconf import DictConfig

from food_on_the_fly import evaluate_model, predict_model, train_model
from food_on_the_fly.data import loaders, temporal_split

Workspace = tuple[DictConfig, Path]

CONFIG_DIR = str(Path(__file__).resolve().parents[1] / "configs")
N_ROWS = 900
N_DAYS = 70  # 40-day baseline plus 30 days of "production" weeks


def _synthetic_orders(seed: int = 0) -> pd.DataFrame:
    """Zomato-shaped orders whose delivery time depends on distance and traffic."""
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2022-02-01")
    days = rng.integers(0, N_DAYS, N_ROWS)
    rlat = rng.uniform(12.9, 13.1, N_ROWS)
    rlon = rng.uniform(77.5, 77.7, N_ROWS)
    dlat = rlat + rng.uniform(-0.08, 0.08, N_ROWS)
    dlon = rlon + rng.uniform(-0.08, 0.08, N_ROWS)
    traffic = rng.choice(["Low", "Medium", "High", "Jam"], N_ROWS)
    dist_km = np.hypot(dlat - rlat, dlon - rlon) * 111
    traffic_min = pd.Series(traffic).map({"Low": 0, "Medium": 4, "High": 8, "Jam": 14})
    minutes = 12 + 2.2 * dist_km + traffic_min.to_numpy() + rng.normal(0, 2, N_ROWS)
    hours = rng.integers(8, 23, N_ROWS)
    return pd.DataFrame(
        {
            "ID": [f"0x{i:04x}" for i in range(N_ROWS)],
            "Delivery_person_ID": [f"BANGRES{i % 20:02d}DEL01" for i in range(N_ROWS)],
            "Delivery_person_Age": rng.integers(20, 40, N_ROWS).astype(float),
            "Delivery_person_Ratings": rng.uniform(3.5, 5.0, N_ROWS).round(1),
            "Restaurant_latitude": rlat,
            "Restaurant_longitude": rlon,
            "Delivery_location_latitude": dlat,
            "Delivery_location_longitude": dlon,
            "Order_Date": [
                (start + pd.Timedelta(days=int(d))).strftime("%d-%m-%Y") for d in days
            ],
            "Time_Orderd": [f"{h:02d}:15" for h in hours],
            "Time_Order_picked": [f"{h:02d}:25" for h in hours],
            "Weather_conditions": rng.choice(["Sunny", "Cloudy", "Fog"], N_ROWS),
            "Road_traffic_density": traffic,
            "Vehicle_condition": rng.integers(0, 3, N_ROWS),
            "Type_of_order": rng.choice(["Snack", "Meal", "Drinks", "Buffet"], N_ROWS),
            "Type_of_vehicle": rng.choice(["motorcycle", "scooter"], N_ROWS),
            "multiple_deliveries": rng.integers(0, 3, N_ROWS).astype(float),
            "Festival": rng.choice(["No", "Yes"], N_ROWS, p=[0.9, 0.1]),
            "City": rng.choice(["Urban", "Metropolitian", "Semi-Urban"], N_ROWS),
            "Time_taken (min)": minutes.round(0),
        }
    )


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Workspace]:
    """Point every entry point at a throwaway directory and return a Hydra config."""
    raw_csv = tmp_path / "orders.csv"
    _synthetic_orders().to_csv(raw_csv, index=False)

    processed = tmp_path / "processed"
    monkeypatch.setattr(temporal_split, "PROCESSED_DATA_DIR", processed)
    monkeypatch.setattr(loaders, "PROCESSED_DATA_DIR", processed)
    monkeypatch.setenv("MLFLOW_ALLOW_FILE_STORE", "true")
    monkeypatch.chdir(tmp_path)  # metrics.txt, plots and logs/ land here

    overrides = [
        f"data.source_uri={raw_csv}",
        f"mlflow.tracking_uri=file:{tmp_path / 'mlruns'}",
        "mlflow.experiment_name=e2e_test",
        f"paths.models_dir={tmp_path / 'models'}",
        "model.parameters.n_estimators=30",
    ]
    previous_uri = mlflow.get_tracking_uri()
    with initialize_config_dir(config_dir=CONFIG_DIR, version_base=None):
        cfg = compose(config_name="config", overrides=overrides)
    yield cfg, tmp_path
    mlflow.set_tracking_uri(previous_uri)


def _runs(cfg: DictConfig) -> pd.DataFrame:
    mlflow.set_tracking_uri(cfg.mlflow.tracking_uri)
    return mlflow.search_runs(experiment_names=[cfg.mlflow.experiment_name])


def test_split_train_evaluate_predict(workspace: Workspace) -> None:
    cfg, root = workspace
    processed = root / "processed"

    # 1. Temporal split: baseline files plus weekly production windows.
    temporal_split.main(cfg)
    for name in ("train.csv", "val.csv", "test.csv"):
        assert (processed / name).stat().st_size > 0
    weeks = sorted(processed.glob("week*.csv"))
    assert weeks, "production period should be cut into weekly files"
    train = pd.read_csv(processed / "train.csv")
    test = pd.read_csv(processed / "test.csv")
    assert pd.to_datetime(train["Order_Date"], format="%d-%m-%Y").max() <= (
        pd.to_datetime(test["Order_Date"], format="%d-%m-%Y").min()
    ), "train must not contain orders later than test"

    # 2. Training: CML outputs, saved pipeline, MLflow run with metrics.
    train_model.main(cfg)
    metrics = (root / "metrics.txt").read_text()
    assert "VALIDATION METRICS" in metrics
    for png in (
        "prediction_scatter.png",
        "residual_plot.png",
        "error_distribution.png",
        "feature_importance.png",
    ):
        assert (root / png).stat().st_size > 0
    pipeline_path = root / "models" / "pipeline.joblib"
    assert pipeline_path.exists()
    runs = _runs(cfg)
    assert len(runs) == 1
    val_rmse = float(runs["metrics.val_rmse"].iloc[0])
    assert 0 < val_rmse < 10, "the synthetic target is easy; RMSE should be small"

    # 3. Evaluation on the held-out test split, logged as its own run.
    evaluate_model.main(cfg)
    runs = _runs(cfg)
    eval_runs = runs[runs["tags.mlflow.runName"].str.startswith("eval_")]
    assert len(eval_runs) == 1
    assert float(eval_runs["metrics.test_rmse"].iloc[0]) > 0

    # 4. Batch prediction with the saved pipeline.
    out = root / "predictions.csv"
    scored = predict_model.predict(pipeline_path, processed / "test.csv", out)
    assert out.exists()
    assert len(scored) == len(test)
    assert scored[predict_model.PREDICTION_COL].between(0, 120).all()
    one = joblib.load(pipeline_path).predict(test.head(1))[0]
    assert isinstance(one, float | np.floating)


@pytest.mark.parametrize("mode", ["best", "specific"])
def test_evaluate_selection_modes(workspace: Workspace, mode: str) -> None:
    cfg, _ = workspace
    temporal_split.main(cfg)
    train_model.main(cfg)
    run_id = _runs(cfg)["run_id"].iloc[0]

    cfg.evaluation.selection_mode = mode
    cfg.evaluation.run_id = run_id if mode == "specific" else None
    evaluate_model.main(cfg)

    eval_runs = _runs(cfg)
    eval_runs = eval_runs[eval_runs["tags.mlflow.runName"].str.startswith("eval_")]
    assert eval_runs["params.parent_run_id"].tolist() == [run_id]


def test_evaluate_without_experiment_logs_and_returns(workspace: Workspace) -> None:
    cfg, _ = workspace
    cfg.mlflow.experiment_name = "does_not_exist"
    evaluate_model.main(cfg)  # must not raise


def test_predict_cli(workspace: Workspace) -> None:
    cfg, root = workspace
    temporal_split.main(cfg)
    train_model.main(cfg)
    out = root / "cli_predictions.csv"
    predict_model.main(
        [
            "--model-path",
            str(root / "models" / "pipeline.joblib"),
            "--input",
            str(root / "processed" / "val.csv"),
            "--output",
            str(out),
        ]
    )
    assert predict_model.PREDICTION_COL in pd.read_csv(out).columns


def test_feature_importance_report(workspace: Workspace) -> None:
    pytest.importorskip("seaborn")
    from food_on_the_fly.analysis import feature_importance

    cfg, root = workspace
    temporal_split.main(cfg)
    train_model.main(cfg)
    ranked = feature_importance.main(
        model_path=root / "models" / "pipeline.joblib", top_n=5, save_plot=False
    )
    assert list(ranked.columns) == ["feature", "importance"]
    assert ranked["importance"].is_monotonic_decreasing
    # Distance drives the synthetic target, so it should rank near the top.
    assert any("distance" in f or "haversine" in f for f in ranked["feature"].head(5))
