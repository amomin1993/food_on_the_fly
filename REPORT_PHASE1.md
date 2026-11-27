# Food on the Fly: Phase 1 Report

**Course:** SE 489 Machine Learning Engineering for Production (MLOps), DePaul University

**Author:** Abdul Momin (Modeling Lead)

**Repository:** https://github.com/amomin1993/food_on_the_fly

**Checklist with evidence:** [PHASE1.md](PHASE1.md)

**Other reports:** [Phase 2](REPORT_PHASE2.md) and [Phase 3](REPORT_PHASE3.md)

**Team (Spring 2026):** Jose Muniz (project lead, platform), Aviv Katz (training pipeline, CML, Docker), Imran Ahmed (data, tests, load testing, UI), Abdul Momin (modeling, profiling, CML comparison)

This is the Phase 1 report! It covers the project design, the data handling and the baseline model. Phase 1 was built by the team (including me) back in the spring. The team's original write-up is still in the repo as 'REPORT.md' and I did not touch it, this is so that it can be compared side by side with this one. Sections 3 to 6 are about my own part in the spring, what I fixed for Phase 1 in November, and how the spring version compares to what is here now.

---

## 1. Problem and data

Food delivery apps quote an arrival time usually the moment you submit the order. If the quote is too aggressive, the customers are happy at first but will likely get annoyed. On the other hand, if it's too late or padded they will cancel the order and order somewhere else. The goal of Food on the Fly is to predict the delivery time in minutes from what is known at order time:
1. Courier age and rating
2. Restaurant coordinates
3. Drop-off coordinates
4. Order date and time
5. Weather
6. Traffic Density
7. Vehicle Type
8. Vehicle Condition
9. Order Type
10. Number of Deliveries (Concurrent)
11. Festival Flag
12. City Tier

We used the Zomato (Indian delivery service) delivery operations analytics dataset from Kaggle, roughly containing 45,000 orders across Indian cities. The target is 'Time_taken (min)'. The split is chronological and not random. The first 40 days are the modeling window (split 70/15/15) train, validation, and test respectively. Every later week is held back as simulated production traffic, this is so that drift can be measured on data the model has never seen. A random split would leak future orders into the training and the metrics will falsely look better than they would be in production.

## 2. Project design and baseline model

**Repository and workflow.**

The repo follows the course cookiecutter layout with a `src/` package split into:

1. Data
2. Features
3. Models
4. Evaluation
5. Visualization
6. Utils

The order of work is feature or fix -> dev -> main. GitHub Actions blocks any PR that breaks that order.

**Data handling.**

1. 'make_dataset.py' cleans the target, drops bad rows, parses dates, and writes the temporal splits. Assertions check that the split sizes add up and that the drift window starts after the modeling window. The processed CSVs are tracked with DVC.

2. 'tests/test_data_quality.py' validates the raw data: no nulls in critical columns, no negative or zero targets, coordinates inside valid ranges, restaurant and drop-off not at the same point.

**Features.**

Three custom scikit-learn transformers sit inside the pipeline so training and inference compute features the same way: 'HaversineTransformer' (great-circle distance in km between restaurant and customer) 'WeekdayTransformer' and 'RushHourTransformer'.
Numeric columns go through 'StandardScaler' and categoricals through 'OneHotEncoder' with 'handle_unknown="ignore"', all in one 'ColumnTransformer'.

**Model.**

An XGBoost regressor inside the scikit-learn 'Pipeline', configured by Hydra and tracked in MLflow. The Phase 1 baseline (100 trees, depth 6, learning rate 0.1) reached a validation RMSE of 4.01 minutes, MAE 3.19 and R² 0.821, with training R² 0.835, so overfitting was small.
Seeds are pinned at 42 through 'utils/seed.py'.

## 3. My contribution in the spring

My Phase 1 piece was the first MLflow tracking script, [PR #18](https://github.com/josemunizdev/food_on_the_fly/pull/18) in the team repo (May 7). It trained a simple linear regression on fake delivery data and logged the parameters and metrics (MAE, RMSE, MAPE) to MLflow. The goal was to make sure the tracking setup actually worked before the real pipeline was ready. Once the XGBoost pipeline in 'train_model.py' took over, the script was not needed anymore and it was removed in PR #40 (the Phase 1 feedback also asked for this).

The rest of Phase 1 was done by my teammates:

1. Jose: the repo scaffold, CI and the branch rules
2. Aviv: the Hydra, MLflow and XGBoost training pipeline
3. Imran: the EDA notebook

The full table is in the [README](README.md#team-contributions).

## 4. What I changed in November

When I picked the project back up in November, I went through the Phase 1 checklist one item at a time. Most of the work was already done, it was just never written down:

1. 'PHASE1.md' had 10 of its 46 items unchecked. Most of them were marked as pending even though the work was already in the repo. Now 45 are checked and each one points to a file or a line range. The only one left is data augmentation, which does not apply to tabular regression.
2. The contribution summary in the README was 8 empty checkboxes and my row in the team table still said TBD. Both are filled in now, with PR numbers for every member.
3. 'CONTRIBUTING.md' already existed, but 'PHASE1.md' still said it was "to be created". I added the CI/CD and PR testing rules to it and fixed the checklist.
4. 'PHASE1.md' said the project needs Python 3.13 or higher, which was wrong. The real range is 3.11 to 3.13 (CI and Docker use 3.11).
5. Two files were still the course template. 'predict_model.py' never made a prediction and 'visualize.py' had classification plots that this project never used. Now batch scoring works and 'visualize.py' has the four evaluation plots that training calls.
6. Four plots and a 'metrics.txt' from a training run were sitting at the repo root. They were listed in '.gitignore' but were still in the repo, so I removed them.
7. 'docs/api.md' and 'docs/getting_started.md' still had commands from the template that do not work here. They match the code now.

## 5. Spring submission and this repository side by side

The spring version is the team repo, https://github.com/josemunizdev/food_on_the_fly (dev branch, last commit June 8). This fork has all of it (every author is still on their own commits) plus my 12 commits from November. You can see the full difference in [this comparison](https://github.com/josemunizdev/food_on_the_fly/compare/dev...amomin1993:food_on_the_fly:main).

| Item | Spring submission | This repository |
| --- | --- | --- |
| 'PHASE1.md' | 36 of 46 items checked | 45 of 46 checked, each with a file or line reference |
| Phase 1 report | 'REPORT.md' | 'REPORT.md' unchanged, plus this report |
| Contribution summary in README | 8 empty checkboxes, TBD rows in the team table | Filled in, with PR numbers per member |
| 'CONTRIBUTING.md' | Present, but listed as pending in 'PHASE1.md' | CI/CD and PR testing rules added, checklist updated |
| 'predict_model.py' | Template stub | Scores a CSV with the saved pipeline |
| 'visualize.py' | Unused classification plots | The four evaluation plots used in training |
| 'baseline_model.py' | Removed in May (PR #40) | Not present |

## 6. Phase 1 feedback

The Phase 1 feedback had three suggestions, and this is where each one stands:

1. Fill in the per-member contribution summary. Done in November, see [My Contributions](README.md#my-contributions-abdul-momin) and [Team Contributions](README.md#team-contributions) in the README.
2. Remove or consolidate 'baseline_model.py'. Removed back in May by PR #40.
3. Add a 'CONTRIBUTING.md'. Jose added it in May (PR #23) and I extended it in November.
