# Food on the Fly: Phase 2 Report

**Course:** SE 489 Machine Learning Engineering for Production (MLOps), DePaul University

**Author:** Abdul Momin (Modeling Lead)

**Repository:** https://github.com/amomin1993/food_on_the_fly

**Checklist with evidence:** [PHASE2.md](PHASE2.md)

**Other reports:** [Phase 1](REPORT_PHASE1.md) and [Phase 3](REPORT_PHASE3.md)

**Team (Spring 2026):** Jose Muniz (project lead, platform), Aviv Katz (training pipeline, CML, Docker), Imran Ahmed (data, tests, load testing, UI), Abdul Momin (modeling, profiling, CML comparison)

This is the Phase 2 report. It covers containers, debugging, monitoring, profiling, experiment tracking and logging. Phase 2 was graded in the spring on the team's main branch as of May 21 (commit [2790cb1](https://github.com/josemunizdev/food_on_the_fly/commit/2790cb1)). The team kept fixing things after that date, and I finished what was left on my own in November. Section 4 goes through the grading feedback one item at a time and says who fixed it and when, this is so that it can be matched against the spring submission.

---

## 1. What was built

**Docker.**

'dockerfiles/Dockerfile' is a two-stage build on 'python:3.11-slim-bookworm'. The builder stage installs dependencies into '/root/.local' and the runtime stage copies them over, which keeps compilers and caches out of the final image.
'docker-compose.yaml' mounts 'data/', 'models/', 'mlruns/' and gcloud credentials. A second image, 'dockerfiles/Dockerfile.api', runs the FastAPI service for Phase 3.

Both images are built on every pull request, and the API image is started and called before a PR can merge. To check that the container behaves the same as a laptop, I ran the training image as a Vertex AI job and trained the same config locally on the same data. Both used scikit-learn 1.9.1 and XGBoost 3.2.0 and produced identical metrics down to four decimal places (validation RMSE 3.95, MAE 3.12, R² 0.8234), so the container adds no hidden differences.

**Debugging.**

'docs/debugging/README.md' covers:

1. pdb and ipdb
2. Three ways to debug inside a container
3. Two worked scenarios: NaN loss during training, and a model that predicts the same value for every row

**Monitoring.**

MLflow system metrics are on for every run, and a 'SystemMetricsLogger' context manager samples CPU, memory and process RSS while the model fits. Training duration is logged as its own metric so slow runs stand out.

**Profiling and optimization.**

This was my main Phase 2 piece! cProfile showed that the model itself is cheap to train (about 0.2 s for 50 trees) and that a developer mostly waits on imports and on MLflow logging the model. In May, MLflow worked out the model's pip requirements on every run by scanning the environment.

1. Passing an explicit requirements list and the cloudpickle serializer to 'log_model' cut its time from 1.05 s to 0.64 s.
2. The whole training entry point went from 4.09 s to 3.50 s (median of three warm runs), with validation RMSE unchanged.
3. The May write-up had claimed a 68% cut. When I re-measured, that number turned out to compare a cold first run with a warm second one, so I replaced it with the measured figures.
4. The same change is also what keeps training working on current MLflow, which by default refuses to save our custom transformers.

Details and raw profiles are in 'docs/profiling/OPTIMIZATIONS.md' and 'reports/profiling/'.

**Experiment tracking.**

Three Hydra model configs ('xgboost_baseline', 'xgboost_fast', 'xgboost_optimized') plus an 18-run sweep in 'configs/sweep.yaml'. Run names include trees, depth and learning rate, so the MLflow compare view is readable without opening each run.

'evaluate_model.py' does the following:

1. Picks the latest run, the best run by any metric, or a specific run ID
2. Scores it on the test split
3. Copies the training hyperparameters onto the evaluation run
4. Flags overfitting when test RMSE is more than 10% worse than validation

Results on the current feature set (trained and evaluated on 2026-11-15):

| Config | Trees / depth / learning rate | Train RMSE | Val RMSE | Val MAE | Val R² | Test RMSE | Test R² |
| --- | --- | --- | --- | --- | --- | --- | --- |
| xgboost_baseline | 50 / 3 / 0.10 | 4.73 | 4.83 | 3.81 | 0.736 | 4.74 | 0.747 |
| xgboost_fast | 200 / 3 / 0.05 | 4.52 | 4.63 | 3.66 | 0.757 | 4.54 | 0.768 |
| xgboost_optimized | 200 / 8 / 0.05 | 3.24 | 3.95 | 3.12 | 0.823 | 3.89 | 0.830 |

RMSE and MAE are in minutes. What stood out:

1. Deeper trees matter more than more trees. Going from depth 3 to depth 8 cuts validation RMSE by almost a minute.
2. The optimized config has the biggest gap between train and validation, but its test RMSE is slightly better than validation, so it is not overfitting the modeling window.
3. The baseline config is the one CML trains on every PR because it finishes in seconds.

**Logging.**

One 'setup_logging()' function sets up a Rich console handler and a rotating file handler ('logs/food_on_the_fly.log', 10 MB, 5 backups). Every module gets a named logger.

## 2. My contribution in the spring

Like I said above, profiling was my part of Phase 2. [PR #42](https://github.com/josemunizdev/food_on_the_fly/pull/42) (May 28) committed the first cProfile output to 'reports/profiling/' and changed 'log_model' to pass an explicit requirements list, so MLflow does not have to scan the environment on every run.

I also opened PR #41 for a rotating file handler writing to 'logs/training.log'. That one was closed without merging, and the rotating file log ended up going in through Aviv's PR #40.

The Docker image, the system metrics logger, the Hydra configs and sweep, the evaluation script and the logging setup were done by my teammates (Jose and Aviv). The full table is in the [README](README.md#team-contributions).

## 3. What I changed in November

1. **My optimization had been reverted.** A later merge (#59) put back the bare 'log_model' call. I restored the explicit requirements and added the cloudpickle serializer, which is also what keeps training working on current MLflow.
2. **The profiling numbers were wrong.** The May write-up claimed a 68% cut, but that number compared a cold first run with a warm second one. I measured it again (1.05 s to 0.64 s for 'log_model', 4.09 s to 3.50 s for the whole run), committed the "before" profile next to the "after" one in 'reports/profiling/', and fixed 'docs/profiling/OPTIMIZATIONS.md'.
3. **'PHASE2.md' cited evidence that did not exist.** It listed MLflow run IDs 'abc123' and 'def456', a "vectorized haversine, 8x faster" optimization that was never made, and files that were never committed. I replaced every item with a real file, line range, commit or measured result, and left items unchecked where the work was not done.
4. **Duplicate log lines.** The handler-clearing loop in 'setup_logging()' was commented out, so each call stacked another handler. Fixed.
5. **Unused 'training:' block.** Two model configs still had a 'training:' block (early stopping rounds and verbose) that nothing was reading. Removed.
6. **Container vs laptop.** I ran the training image on Vertex AI and the same config locally, and got identical metrics. This is the environment consistency item in 'PHASE2.md'.
7. **Docker in CI.** Both images now get built on every pull request, and the API container is started and called before a PR can merge.
8. **Results re-run.** The results table in section 1 is from November 15, on the current feature set.
9. **README and logs.** I added the Testing and Troubleshooting sections to the README, plus sample training and inference logs in 'docs/logs/'.

Two items are still open and I left them unchecked in 'PHASE2.md' on purpose:

1. GPU profiling, it does not apply because XGBoost runs on CPU here
2. A second measured optimization, which was not done

## 4. Phase 2 feedback, item by item

'PHASE2.md' was the unfilled template when Phase 2 was graded. By the end of the spring it had 60 of 64 items checked, and now it has 64 of 66. Everything added since the team's last commit is in [this comparison](https://github.com/josemunizdev/food_on_the_fly/compare/dev...amomin1993:food_on_the_fly:main).

| Feedback | Where it stands | Who and when |
| --- | --- | --- |
| Dockerfile on 'python:3.13-slim' | 'python:3.11-slim-bookworm' in both Dockerfiles | Aviv, PR #36, May |
| 'PHASE2.md' was the unfilled template | Filled in with evidence | Aviv filled it in during May and June (#37, #40, #43). I replaced the placeholder evidence in November |
| No profiling output committed | 'reports/profiling/' | Me, PR #42, May. The "before" profile was added in November |
| No Scalene or py-spy, no documented optimization | 'scalene-profile.html', 'docs/profiling/OPTIMIZATIONS.md' and the 'log_model' optimization | Aviv, PR #40, for Scalene and the document. The optimization is mine (#42), restored and re-measured in November |
| No rotating file log under 'logs/' | 'RotatingFileHandler' writing to 'logs/food_on_the_fly.log' | Aviv, PR #40. The duplicate handler fix is mine, November |
| No Phase 2 sections in the README | README section "Phase 2: Docker, Monitoring, Profiling & Debugging" | Aviv, PR #40. Testing and Troubleshooting are mine, November |
| No debugging documentation | 'docs/debugging/README.md' | Aviv, PR #40. Updated by me in November |
| 'baseline_model.py' still present | Removed | Aviv, PR #40 |
| Unused 'training:' block in the configs | Removed from 'configs/model/' | Me, November |
| Contribution checkboxes empty, no contribution table | Filled in, see the [README](README.md#my-contributions-abdul-momin) | Me, November |
