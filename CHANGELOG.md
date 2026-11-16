# Changelog

All notable changes to Food on the Fly. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions follow
[Semantic Versioning](https://semver.org/). Tags matching `v*.*.*` trigger
`.github/workflows/deploy.yml`.

## [1.1.0] - 2026-11-15

### Added
- `docker-build` CI job: builds training and API images on every PR and push to
  `main`, then smoke-tests `/health` and `/predict` in a running container.
- Python 3.12 added to the CI test matrix, coverage summary printed in CI.
- `docs/http_api.md` (endpoints, schemas, real request/response examples, error codes).
- `docs/architecture.md` (data, training, serving and CI/CD diagrams).
- Testing and troubleshooting sections in `README.md`, CI/CD and PR testing
  requirements in `CONTRIBUTING.md`.
- Cloud Run deployment in the project's own GCP: `scripts/gcp_setup.sh`
  (Artifact Registry, dataset bucket, service accounts, Workload Identity
  Federation, first deploy, smoke test, load test), `DEPLOYMENT.md`, `CLEANUP.md`.
- Cloud Monitoring dashboard and 5xx alert policy (`scripts/gcp_monitoring.sh`,
  `deploy/monitoring/`).
- Sample training, inference and load test logs in `docs/logs/`.

### Fixed
- CI format check failing on Markdown code blocks after a ruff upgrade.
- API image now serves the committed `models/pipeline.joblib` (`MODEL_PATH`), so
  `/predict` works on Cloud Run instead of returning 503.
- `setup_logging()` is idempotent, so log lines are no longer duplicated.
- Model logging on MLflow 3.x: `serialization_format="cloudpickle"` plus explicit
  requirements (skops rejected the custom transformers; inference conflicted
  with `uv.lock`).
- Restored explicit `pip_requirements` in `mlflow.sklearn.log_model`, which had been
  reverted in #59.

### Changed
- Phase 1-3 checklists rewritten so every ticked item points at a real file,
  commit or run.
- Raw data and deploys moved from the team's GCP project to `food-on-the-fly`;
  Cloud Run capped at 0-2 instances.
- Profiling re-measured; the May "68% faster" figure corrected.

## [1.0.0] - 2026-06-08

### Added
- FastAPI inference service with `/health`, `/predict`, `/predict/batch` (#48).
- Cloud Run deploy workflow with Artifact Registry push, version-tag trigger (#46).
- CML workflow that trains on the runner and comments metrics and plots on PRs (#44).
- Current-vs-baseline model comparison in the CML report (#53) and CML docs (#56).
- Config-driven feature toggles and leakage-safe temporal split (#52).
- Load test script (#55), Gradio UI (#59), concept drift simulation (#60).

## [0.2.0] - 2026-05-29

### Added
- Multi-stage Docker image on `python:3.11-slim-bookworm`, docker-compose.
- cProfile and Scalene profiling scripts and reports, Hydra multirun sweep (#30).
- MLflow system metrics, evaluation script with latest/best/specific modes (#36).
- Multi-model Hydra configs: baseline, fast, optimized (#37).
- RichHandler + RotatingFileHandler logging (#40).

### Changed
- `log_model` passes explicit `pip_requirements`, cutting training wall-clock (#42).

## [0.1.0] - 2026-05-07

### Added
- Cookiecutter project layout, Hydra config, MLflow tracking, XGBoost pipeline (#16, #18).
- DVC-tracked temporal train/val/test/drift splits, EDA notebook (#20).
- Haversine distance transformer, pytest suite, ruff and mypy in CI (#21).
- Branch rules: `feature/*` or `fix/*` into `dev`, only `dev` into `main`.
