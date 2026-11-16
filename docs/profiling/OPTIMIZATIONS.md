# Profiling and Optimization

## How to profile

```bash
make profile                      # cProfile -> reports/profiling/train_model.{prof,txt}
python scripts/profile_scalene.py # Scalene CPU + memory -> reports/profiling/scalene_report.json
snakeviz reports/profiling/train_model.prof   # interactive view
```

## Baseline profile

Measured with `make profile` on the `xgboost_baseline` config, 20,838 training rows.
Environment: Linux x86_64, Python 3.11, dependencies from `uv.lock`
(mlflow 3.13.0, scikit-learn 1.9.0, xgboost 3.2.0), warm package cache.

Where the ~7 s of a profiled run goes (`reports/profiling/train_model_before.txt`):

| Step | Cumulative time | Share |
| --- | --- | --- |
| Module imports (mlflow, sklearn, xgboost, hydra) | ~3.9 s | ~56% |
| `mlflow.sklearn.log_model` | 0.97 s | ~14% |
| XGBoost fit (50 trees) | ~0.2 s | ~3% |
| Everything else (data load, metrics, CML plots) | remainder | |

The model itself is cheap to train. The two things a developer waits on are
imports and MLflow model logging.

Scalene (`reports/profiling/scalene_report.json`, run by the team in May on
macOS) recorded a 10.3 s run with a peak memory footprint of about 4.9 GB,
attributed to the import block at the top of `train_model.py`.

## Optimization 1: explicit requirements and serializer in `log_model`

**Problem.** `mlflow.sklearn.log_model(pipeline, "model")` works out the
model's pip requirements on every run by inspecting the environment. In May,
cProfile showed `infer_pip_requirements` taking 4.19 s of a 13.74 s run.

**Change** (`src/food_on_the_fly/train_model.py`):

```python
mlflow.sklearn.log_model(
    pipeline,
    "model",
    serialization_format="cloudpickle",
    pip_requirements=["scikit-learn", "xgboost", "pandas", "numpy", "cloudpickle"],
)
```

**Re-measured in November** with the current `uv.lock`, three runs each,
median, same machine, warm cache (`train_model_before.*` vs `train_model.*`):

| Metric | Before | After | Change |
| --- | --- | --- | --- |
| `log_model` cumulative time | 1.05 s | 0.64 s | −0.41 s (−39%) |
| Training entry point end to end | 4.09 s | 3.50 s | −0.59 s (−14%) |
| Validation RMSE | 4.83 min | 4.83 min | unchanged |

**Correcting the May number.** The May write-up reported 13.74 s → 4.45 s, a
68% cut. That comparison mixed a cold first run with a warm second run: in
November the very first run after a fresh install took 7.27 s and the next
ones about 4.1 s with no code change at all. Only the time inside
`log_model` is attributable to this change, and on today's MLflow the
inference step is much cheaper than it was in May (about 0.05 s), so the
saving that can be attributed to it is the 0.4 s in the table above.

**Why it still matters: it makes training work on current MLflow.** CI
installs the newest MLflow that `pyproject.toml` allows (3.18 in November).
There, the bare `log_model` call fails in two ways:

1. MLflow now defaults to the `skops` serializer, which refuses to save our
   custom transformers (`HaversineTransformer`, `RushHourTransformer`,
   `WeekdayTransformer`) and the XGBoost booster as "untrusted types".
2. Requirement inference reads the pinned versions from `uv.lock`
   (scikit-learn 1.9.0) and conflicts with the newer version pip installed
   (1.9.1), raising `ResolutionImpossible`.

Passing `serialization_format="cloudpickle"` and explicit `pip_requirements`
avoids both, so the same code trains under the lockfile and under the latest
releases.

## Optimization 2: not implemented

The profile points at imports (~56% of a run). Moving the heavy imports in
`train_model.py` (mlflow, xgboost, the CML plotting stack) inside the
functions that use them would mainly help short CLI calls like `--help` or a
config check. It was identified and not implemented.
