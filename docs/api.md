# API Reference

The package is importable as `food_on_the_fly` after running `pip install -e .`.

## `food_on_the_fly.config`

Project-wide path constants and the Hydra config loader.

```python
from food_on_the_fly.config import (
    PROJECT_ROOT,
    DATA_DIR,
    RAW_DATA_DIR,
    PROCESSED_DATA_DIR,
    MODELS_DIR,
    REPORTS_DIR,
    FIGURES_DIR,
    CONFIG_DIR,
    load_config,
)
```

Use these constants instead of hard-coded relative paths — they resolve against the repo root regardless of the current working directory.

## `food_on_the_fly.logging_config`

```python
from food_on_the_fly.logging_config import setup_logging, get_logger

setup_logging(level="INFO")
logger = get_logger(__name__)
```

## `food_on_the_fly.data`

| Function | Purpose |
|---|---|
| `load_raw(filename)` | Read CSV from `data/raw/` |
| `load_processed(filename)` | Read CSV from `data/processed/` |
| `save_processed(df, filename)` | Write CSV to `data/processed/` |
| `load_dataset(uri)` | Read a CSV from a local path or a `gs://` URI |

CLI: `python -m food_on_the_fly.data.temporal_split [data.source_uri=PATH]`

## `food_on_the_fly.features`

```python
from food_on_the_fly.features import build_features

df_features = build_features(df_processed, cfg)  # cfg: the Hydra config
```

## `food_on_the_fly.models`

### `BaseModel` (abstract)

Abstract interface with `fit`, `predict`, `save`, `load`. Extend this for any new estimator.

### `Model`

Reference implementation scaffold. Serializes via `joblib`.

```python
from pathlib import Path
from food_on_the_fly.models import Model

model = Model(config={"lr": 0.01})
# model.fit(X_train, y_train)
model.save(Path("models/model.joblib"))
reloaded = Model.load(Path("models/model.joblib"))
```

## `food_on_the_fly.evaluation`

```python
from food_on_the_fly.evaluation import regression_report

metrics = regression_report(y_true, y_pred)
# -> {"mae": ..., "mse": ..., "rmse": ..., "r2": ...}
```

## `food_on_the_fly.visualization`

```python
from food_on_the_fly.visualization import (
    plot_error_distribution,
    plot_feature_importance,
    plot_prediction_scatter,
    plot_residuals,
)
```

## `food_on_the_fly.utils`

```python
from food_on_the_fly.utils import set_seed, save_json, load_json

set_seed(42)
```

## Training / Prediction CLIs

```bash
python -m food_on_the_fly.train_model model=xgboost_optimized
python -m food_on_the_fly.predict_model --model-path models/pipeline.joblib --input data/processed/test.csv
```

## Hydra Configuration

Configuration is managed through Hydra — see `configs/config.yaml` for defaults and override at runtime:

```bash
python -m food_on_the_fly.train_model model=xgboost_fast model.parameters.n_estimators=300
```

---

**Food on the Fly** · Version see `food_on_the_fly.__version__`
