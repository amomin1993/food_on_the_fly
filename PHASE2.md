# PHASE 2: Enhancing ML Operations with Containerization & Monitoring

## Overview

Phase 2 focuses on scaling and operationalizing Food on the Fly by implementing containerization, advanced monitoring, profiling, experiment tracking, and comprehensive logging. This phase ensures your model can be reliably deployed, monitored in production, and continuously improved through systematic experimentation.

---

## 1. Containerization

- [x] **Dockerfile Creation**: Build Dockerfile for model training and inference
  - Evidence: `dockerfiles/Dockerfile` (training image), `dockerfiles/Dockerfile.api` (FastAPI inference image)
- [x] **Base Image Selection**: Choose appropriate base image (python:3.x, nvidia/cuda, etc.)
  - Evidence: `python:3.11-slim-bookworm` in a two-stage build, `dockerfiles/Dockerfile` lines 5 and 13. Slim Debian keeps the image small and CPU-only XGBoost needs no CUDA base.
- [x] **Environment Variables**: Define and document required environment variables
  - Evidence: `dockerfiles/Dockerfile` lines 21-22 (`PATH`, `PYTHONUNBUFFERED`); `dockerfiles/Dockerfile.api` adds `PORT` and `MODEL_PATH`; `docker-compose.yaml` sets `GOOGLE_APPLICATION_CREDENTIALS` and `GOOGLE_CLOUD_PROJECT`
- [x] **Build Instructions**: Document how to build Docker image with examples
  - Evidence: `README.md` section "Docker Usage" (line 131)
- [x] **Run Instructions**: Document how to run container with proper volume/network config
  - Evidence: `README.md` section "Docker Usage", volume mounts for `data/`, `mlruns/`, `logs/`
- [x] **Container Testing**: Test container locally to ensure consistency with host environment
  - Evidence: CI job `PR checks / Build and smoke-test Docker images` (`.github/workflows/pr-checks.yml`) builds both images on every PR, starts the API container and asserts `/health` reports a loaded model and `/predict` returns a delivery time; it passed on PR #1. The same API image is the one deployed to Cloud Run (see PHASE3.md)
- [x] **Docker Compose (Optional)**: Create docker-compose.yml for multi-service setups
  - Evidence: `docker-compose.yaml` (mounts data, models, mlruns and gcloud credentials; exposes 8000 and 5001 on a bridge network)
- [ ] **Environment Consistency**: Verify that containerized training produces identical results to local training
  - Not verified end to end: the training image is built in CI but training is not run inside it there, because the dataset is not baked into the image. Seeds are pinned (`random_state: 42`) and repeated local runs give identical metrics (val RMSE 4.83 for `xgboost_baseline`)

---

## 2. Monitoring & Debugging

- [x] **Debugging Tools**: Set up pdb/ipdb for interactive debugging
  - Evidence: `docs/debugging/README.md` sections "Installation" and "Basic pdb/ipdb Commands"
- [x] **Debugging Documentation**: Document how to debug in containerized environment
  - Evidence: `docs/debugging/README.md` section "Debugging in Docker" (interactive container, attach to running container, VS Code remote)
- [x] **Debug Scenario 1**: Model training fails with NaN loss
  - Evidence: `docs/debugging/README.md` "Debugging Scenario 1"
- [x] **Debug Scenario 2**: All predictions are identical
  - Evidence: `docs/debugging/README.md` "Debugging Scenario 2"
- [x] **Logging for Debugging**: Implement detailed logging at critical points in code
  - Evidence: `src/food_on_the_fly/train_model.py` lines 61 (resolved config), 83-114 (data loading and sample counts), 183 (enabled transformers), 194-200 (training start and duration), 229-239 (train/val metrics)
- [x] **Model Assertion Checks**: Add assertions to catch data/model anomalies early
  - Evidence: `src/food_on_the_fly/data/make_dataset.py` lines 82-90 (split sizes must sum to the dataset, and the drift window must start after the modeling window so no future data leaks into training)
- [x] **Training Validation**: Implement sanity checks (NaN detection, shape validation, etc.)
  - Evidence: `tests/test_data_quality.py` (no nulls, no negative or zero targets, target range, coordinate bounds, restaurant and delivery points not identical, valid city values) and `tests/test_training_pipeline.py`

---

## 3. Profiling & Optimization

- [x] **CPU Profiling**: Use cProfile to profile training and inference
  - Evidence: `scripts/profile_training.py` (`make profile`), output in `reports/profiling/train_model.txt` and `reports/profiling/train_model.prof`
- [x] **Memory Profiling**: Profile memory usage with memory_profiler or similar
  - Evidence: `scripts/profile_scalene.py`, results in `reports/profiling/scalene_report.json` and `scalene-profile.html`
- [ ] **GPU Profiling (if applicable)**: N/A (CPU-only XGBoost)
- [x] **Profiling Results**: Document baseline profiling results and bottlenecks identified
  - Evidence: `docs/profiling/OPTIMIZATIONS.md` section "Baseline profile" (imports ~56% of a run, `log_model` ~14%, XGBoost fit ~3%), `reports/profiling/train_model_before.txt`
- [x] **Optimization 1**: Skip MLflow dependency inference when logging the model
  - Evidence: `src/food_on_the_fly/train_model.py` (`mlflow.sklearn.log_model(..., serialization_format="cloudpickle", pip_requirements=[...])`), `docs/profiling/OPTIMIZATIONS.md`, before/after profiles in `reports/profiling/train_model_before.txt` and `reports/profiling/train_model.txt`
- [ ] **Optimization 2**: Implement and measure additional optimization
- [x] **Performance Benchmarks**: Document before/after performance metrics
  - Evidence: `docs/profiling/OPTIMIZATIONS.md`: `log_model` 1.05 s → 0.64 s (−39%), training entry point 4.09 s → 3.50 s (−14%), median of 3 warm runs each; validation RMSE unchanged. Also corrects the May figure, which compared a cold run with a warm one
- [x] **Optimization Documentation**: Explain each optimization and its impact
  - Evidence: `docs/profiling/OPTIMIZATIONS.md`

---

## 4. Experiment Management & Tracking

- [x] **MLflow Setup**: Initialize MLflow tracking server and client configuration
  - Evidence: `configs/config.yaml` lines 6-9, `src/food_on_the_fly/train_model.py` lines 67-68
- [x] **Metric Logging**: Log training/validation metrics for each experiment
  - Evidence: `src/food_on_the_fly/train_model.py` lines 199 (train duration) and 219-226 (train/val MSE, RMSE, MAE, R²)
- [x] **Parameter Logging**: Hydra params are logged
  - Evidence: `src/food_on_the_fly/train_model.py` lines 73-78 (full resolved config logged with `mlflow.log_params`)
- [x] **System Metrics**: CPU and memory captured per run
  - Evidence: `mlflow.enable_system_metrics_logging()` at `train_model.py` line 72, `src/food_on_the_fly/utils/monitoring.py`
- [x] **Model Artifact Logging**: Pipeline saved to MLflow
  - Evidence: `src/food_on_the_fly/train_model.py` (`mlflow.sklearn.log_model` after the CML outputs), plus `models/pipeline.joblib` for serving
- [x] **Experiment Comparison**: 3+ models trained and compared
  - Evidence: `configs/model/xgboost_baseline.yaml`, `xgboost_fast.yaml`, `xgboost_optimized.yaml`, `make train_all`, sweep in `configs/sweep.yaml` (`make train_sweep`)
- [x] **Visualization**: MLflow UI comparison charts
  - Evidence: `docs/images/test_results/mlflow_comparison_screenshot.png`, `docs/images/Best run as of 5-29-2026.png`
- [x] **Best Model Selection**: Documented selection criteria
  - Evidence: lowest `val_rmse` (ties broken by highest `val_r2`); implemented as `selection_mode=best` in `src/food_on_the_fly/evaluate_model.py`
- [x] **Experiment Documentation**: All runs in MLflow with descriptive names
  - Evidence: `configs/config.yaml` line 9, run names encode model name, trees, depth and learning rate
- [x] **Evaluation script created**
  - File: `src/food_on_the_fly/evaluate_model.py`
  - Supports three evaluation modes: latest, best, specific
  - Evidence: [evaluate_model.py lines 58-112](src/food_on_the_fly/evaluate_model.py#L58-L112)
- [x] **Hyperparameter tracking implemented**
  - Hyperparameters copied from the training run to the evaluation run, with parent run metadata (run_id, run_name)
  - Evidence: [evaluate_model.py lines 138-152](src/food_on_the_fly/evaluate_model.py#L138-L152)
- [x] **Metric comparison implemented**
  - Test vs validation performance comparison, absolute and percentage degradation, overfitting flag above 10% degradation
  - Evidence: [evaluate_model.py lines 172-192](src/food_on_the_fly/evaluate_model.py#L172-L192)
- [x] **Makefile targets added**
  - Evidence: `Makefile` lines 36-46

```bash
make evaluate_best     # Evaluate best model by validation RMSE
make evaluate_latest   # Evaluate most recent model
make evaluate_best_r2  # Evaluate best model by R² score
```

- [x] **Configuration added**
  - Evidence: `configs/config.yaml` lines 11-15 (`evaluation` block: run_id, selection_mode, best_metric, best_metric_order)

---

## 5. Application & Experiment Logging

- [x] **Logger Setup**: RichHandler + RotatingFileHandler configured
  - Evidence: `src/food_on_the_fly/logging_config.py`
- [x] **Log Levels**: DEBUG, INFO, WARNING, ERROR used appropriately
  - Evidence: `train_model.py` (INFO progress, WARNING on config conversion), `evaluate_model.py` (ERROR when a run_id is missing), `utils/monitoring.py` (WARNING when psutil is absent), `api/main.py` (exception logging on failed predictions)
- [x] **Log Messages**: Informative messages at key points
  - Evidence: `train_model.py` lines 61-361 (see section 2)
- [x] **Training Log Example**: Sample training run committed
  - Evidence: `docs/logs/sample_training.log` (resolved config, data loading, enabled transformers, training duration, train/val metrics, MLflow logging)
- [x] **Inference Log Example**: Prediction logs included
  - Evidence: `docs/logs/sample_inference.log` (model load, successful single and batch predictions, a 400 with full traceback for an unparseable date, a 422 for a missing field)
- [x] **Error Logging**: Comprehensive error logging with context
  - Evidence: `api/main.py` `logger.exception(...)` on prediction failure, `api/model_loader.py` warning when the model cannot load at startup
- [x] **Performance Logging**: Training duration logged
  - Evidence: `train_model.py` lines 195-200 (`time.perf_counter`, logged to MLflow as `train_duration_seconds`)
- [x] **Log Rotation**: RotatingFileHandler configured (10MB, 5 backups)
  - Evidence: `src/food_on_the_fly/logging_config.py`

---

## 6. Configuration Management

- [x] **Hydra Setup**: Hydra configured with OmegaConf
  - Evidence: `train_model.py` line 53 (`@hydra.main`), `configs/` directory
- [x] **Config Files**: YAML configs for all components
  - Evidence: `configs/config.yaml`, `configs/model/*.yaml`, `configs/sweep.yaml`
- [x] **Config Structure**: Hierarchical configs (base + model overrides)
  - Evidence: `configs/config.yaml` defaults list
- [x] **Config Example 1**: Baseline training config
  - Evidence: `configs/model/xgboost_baseline.yaml`
- [x] **Config Example 2**: Optimized config
  - Evidence: `configs/model/xgboost_optimized.yaml`
- [x] **Config Validation**: Hydra validates structure automatically
  - Evidence: unknown keys or missing config groups fail at startup
- [x] **Override Documentation**: CLI overrides documented
  - Evidence: `README.md` sections "Custom Hyperparameters" and "Docker Usage" (`HYDRA_ARGS`)
- [x] **Config Version Control**: All configs tracked in git
  - Evidence: `git log -- configs/`

---

## 7. Documentation & Repository Updates

- [x] **README Update**: Includes all Phase 2 sections:
  - [x] Containerization section with Docker usage
    - Evidence: `README.md` "Docker Usage" (line 131)
  - [x] Debugging and profiling guide
    - Evidence: `README.md` "Profiling" (line 190) and "Debugging" (line 273), links to `docs/debugging/` and `docs/profiling/`
  - [x] Experiment tracking setup instructions
    - Evidence: `README.md` "Monitoring & Experiment Tracking" (line 161)
  - [x] Configuration management guide
    - Evidence: `README.md` "Model Configuration" (line 75)
  - [x] Logging usage examples
    - Evidence: `README.md` "Logging" (line 295)
- [x] **Architecture Documentation**: Mermaid diagram in README
  - Evidence: `README.md` "Architecture Diagram" (line 26)
- [x] **Setup Guide**: Updated with Phase 2 tools
  - Evidence: `README.md` "Setup Instructions"
- [x] **Examples**: Running with different configurations
  - Evidence: `README.md`, `Makefile` targets `train_baseline`, `train_fast`, `train_optimized`
- [x] **Tool Integration**: How tools work together documented
  - Evidence: `README.md` Phase 2 section
- [x] **Troubleshooting**: Add troubleshooting section for common issues
  - Evidence: `README.md` "Troubleshooting"
- [x] **Performance Guide**: Document how to profile and optimize
  - Evidence: `docs/profiling/OPTIMIZATIONS.md`, `README.md` "Profiling"
- [x] **Version Compatibility**: Requirements tracked in requirements*.txt
  - Evidence: `requirements.txt`, `requirements_dev.txt`, `pyproject.toml`, `uv.lock`

---

> **Checklist:** Use this as a guide for documenting your Phase 2 deliverables.
