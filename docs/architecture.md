# Architecture

Four views of the system: data, training, serving, and CI/CD. All diagrams are
Mermaid and render on GitHub.

## Data pipeline

```mermaid
flowchart LR
    K[(Kaggle<br/>Zomato delivery dataset)] --> G[(GCS bucket<br/>data/raw/zomato_dataset.csv)]
    G -->|gcsfs, data.source_uri| S[temporal_split.py]
    S --> B[(data/processed<br/>train / val / test<br/>first 40 days, 70/15/15)]
    S --> W[(data/processed<br/>week1..weekN<br/>later weeks for drift)]
    B -. DVC .dvc pointers .-> R[(DVC remote)]
    B --> Q[tests/test_data_quality.py<br/>nulls, ranges, coordinates]
```

The split is chronological so the model never sees orders from after its
training window. Later weeks are kept back as simulated production traffic for
drift checks (`scripts/drift_simulation.py`).

## Training pipeline

```mermaid
flowchart TD
    H[Hydra<br/>configs/config.yaml + configs/model/*.yaml] --> T[train_model.py]
    B[(train.csv / val.csv)] --> T
    subgraph Pipeline [sklearn Pipeline]
        direction LR
        CT[ColumnTransformer<br/>Haversine distance<br/>Weekday, Rush hour<br/>StandardScaler numerics<br/>OneHotEncoder categoricals] --> X[XGBRegressor]
    end
    T --> Pipeline
    Pipeline --> M[(MLflow<br/>params, train/val metrics,<br/>system metrics, model)]
    Pipeline --> J[(models/pipeline.joblib)]
    Pipeline --> C[CML outputs<br/>metrics.txt + 4 plots]
    M --> E[evaluate_model.py<br/>latest / best / specific run<br/>test metrics + degradation]
```

## Serving

```mermaid
flowchart LR
    U[Client<br/>curl / httpx / load_test.py] -->|HTTPS JSON| CR[Cloud Run service<br/>food-on-the-fly-api]
    subgraph CR_box [Container: dockerfiles/Dockerfile.api]
        UV[uvicorn] --> FA[FastAPI<br/>/health /predict /predict/batch]
        FA --> ML[model_loader<br/>MODEL_PATH, else MODEL_URI]
        ML --> P[(pipeline.joblib)]
    end
    CR --> CR_box
    CR_box -->|stdout logs| CL[Cloud Logging]
    CR -->|request count, latency,<br/>instances| CM[Cloud Monitoring]
    AR[(Artifact Registry<br/>api:commit-sha)] -->|image| CR
    GR[Gradio app<br/>app/app.py] -.->|deploy-hf.yml| HF[Hugging Face Spaces]
```

## CI/CD

```mermaid
flowchart TD
    F[feature/* or fix/* branch] -->|PR| D[dev]
    F -->|PR opened| PC[pr-checks.yml<br/>branch rules, ruff lint + format,<br/>mypy, pytest 3.11 + 3.12, coverage,<br/>Docker build + smoke test]
    F -->|PR opened| CML[cml.yml<br/>train baseline config,<br/>compare to reports/baseline_metrics.json,<br/>post report as PR comment]
    D -->|PR| MN[main]
    MN -->|push| PC2[pr-checks.yml on main]
    PC2 -->|workflow_run success| DEP[deploy.yml<br/>build Dockerfile.api,<br/>push to Artifact Registry,<br/>gcloud run deploy]
    TAG[tag vX.Y.Z] --> DEP
    MAN[workflow_dispatch] --> DEP
    DEP --> CR[Cloud Run]
```
