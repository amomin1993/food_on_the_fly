# Deployment Guide

The prediction API runs on **Google Cloud Run** in project `food-on-the-fly`,
region `us-central1`.

**Live URL:** https://food-on-the-fly-api-hhwrf2nw2a-uc.a.run.app
(Swagger UI at `/docs`, health at `/health`)

| Piece | Value |
| --- | --- |
| Cloud Run service | `food-on-the-fly-api` (1 vCPU, 1 GiB, min 0 / max 2 instances, port 8080) |
| Image | `us-central1-docker.pkg.dev/food-on-the-fly/food-on-the-fly/api:<git sha>` |
| Image source | `dockerfiles/Dockerfile.api` (serves `models/pipeline.joblib`) |
| Runtime identity | `fof-api-runtime@food-on-the-fly.iam.gserviceaccount.com` (no roles; the model is baked into the image) |
| CI/CD identity | `github-deployer@food-on-the-fly.iam.gserviceaccount.com` via Workload Identity Federation (no JSON keys) |
| Dataset for CI | `gs://food-on-the-fly-data-amomin/data/raw/zomato_dataset.csv` |

Architecture diagrams: [docs/architecture.md](docs/architecture.md).
Endpoint reference: [docs/http_api.md](docs/http_api.md).

---

## 1. One-time GCP setup

Everything is scripted in [`scripts/gcp_setup.sh`](scripts/gcp_setup.sh). It is
idempotent, so re-running it is safe.

1. Create a project (here `food-on-the-fly`) with billing attached, and a
   budget alert (Billing → Budgets & alerts; this project uses $10 with
   50/90/100% email alerts).
2. Open **Cloud Shell** in that project.
3. Upload the Kaggle dataset zip (Cloud Shell → ⋮ → Upload), then:

```bash
git clone -b dev https://github.com/amomin1993/food_on_the_fly.git && cd food_on_the_fly
mkdir -p data/raw && unzip -o -j ~/Zomato.zip -d data/raw
mv "data/raw/Zomato Dataset.csv" data/raw/zomato_dataset.csv
bash scripts/gcp_setup.sh 2>&1 | tee ~/gcp_setup_log.txt
```

The script:

| Step | What it creates |
| --- | --- |
| APIs | Cloud Run, Artifact Registry, Cloud Build, IAM Credentials, STS, Logging, Monitoring, Storage |
| Artifact Registry | Docker repo `food-on-the-fly` in `us-central1` |
| Storage | Bucket `food-on-the-fly-data-amomin`, uploads the dataset |
| Service accounts | `fof-api-runtime` (runs the API), `github-deployer` (`roles/run.admin`, `roles/artifactregistry.writer`, read on the dataset bucket, `serviceAccountUser` on the runtime SA) |
| Workload Identity Federation | Pool `github`, OIDC provider `github-oidc`, restricted to `assertion.repository == 'amomin1993/food_on_the_fly'` |
| First deploy | Builds `Dockerfile.api` (amd64 in Cloud Shell), pushes, deploys to Cloud Run, grants `allUsers` → `roles/run.invoker` |
| Verification | `curl` of `/health` and `/predict`, then a 60 s load test |

At the end it prints the GitHub Actions secrets.

## 2. GitHub Actions secrets

Settings → Secrets and variables → Actions:

| Secret | Meaning |
| --- | --- |
| `GCP_PROJECT_ID` | `food-on-the-fly` |
| `GCP_REGION` | `us-central1` |
| `GCP_ARTIFACT_REPO` | `food-on-the-fly` |
| `GCP_SERVICE_ACCOUNT` | deployer service account email |
| `GCP_WIF_PROVIDER` | full resource name of the `github-oidc` provider |

No service account keys exist. GitHub's OIDC token is exchanged for a
short-lived Google token, and only workflows from this repository can do the
exchange.

## 3. Continuous deployment

`.github/workflows/deploy.yml` builds `Dockerfile.api`, pushes it tagged with
the commit SHA, and runs `gcloud run deploy` with the same limits as above.
It runs when:

- a PR is merged to `main` and **PR checks** pass on the merge commit
  (`workflow_run` chaining, so an untested commit is never deployed),
- a version tag `vX.Y.Z` is pushed,
- someone clicks **Run workflow** (manual redeploy).

## 4. Manual deploy (no CI)

```bash
IMAGE=us-central1-docker.pkg.dev/food-on-the-fly/food-on-the-fly/api:$(git rev-parse --short HEAD)
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet
docker build --platform linux/amd64 -t "$IMAGE" -f dockerfiles/Dockerfile.api .
docker push "$IMAGE"
gcloud run deploy food-on-the-fly-api --image "$IMAGE" --region us-central1 \
  --port 8080 --cpu 1 --memory 1Gi --min-instances 0 --max-instances 2 \
  --service-account fof-api-runtime@food-on-the-fly.iam.gserviceaccount.com \
  --allow-unauthenticated
```

## 5. Invoking the deployed model

```bash
URL=https://food-on-the-fly-api-hhwrf2nw2a-uc.a.run.app
curl -s "$URL/health"
# {"status":"ok","model_loaded":true,"model_version":"pipeline.joblib"}

curl -s -X POST "$URL/predict" -H "Content-Type: application/json" -d '{
  "Delivery_person_Age": 30.0, "Delivery_person_Ratings": 4.5,
  "Restaurant_latitude": 22.745049, "Restaurant_longitude": 75.892471,
  "Delivery_location_latitude": 22.765049, "Delivery_location_longitude": 75.912471,
  "Order_Date": "19-03-2022", "Time_Orderd": "17:30",
  "Weather_conditions": "Sunny", "Road_traffic_density": "Low",
  "Vehicle_condition": 2, "Type_of_order": "Snack", "Type_of_vehicle": "motorcycle",
  "multiple_deliveries": 0.0, "Festival": "No", "City": "Urban"}'
# {"predicted_time_min":17.52,"model_version":"pipeline.joblib"}
```

## 6. Environment variables and secrets

| Variable | Where | Purpose |
| --- | --- | --- |
| `PORT` | `Dockerfile.api` (8080) | uvicorn port, matches Cloud Run's `--port` |
| `MODEL_PATH` | `Dockerfile.api` | `/app/models/pipeline.joblib`, the baked-in model |
| `MODEL_URI` | optional at deploy time | an MLflow URI to serve instead (`gcloud run deploy ... --set-env-vars MODEL_URI=...`) |

Nothing secret is stored in the image or the repo. CI authenticates with
Workload Identity Federation, and the runtime service account has no
permissions it does not need.

## 7. Load test results

`scripts/load_test.py --rate 600 --duration 60 --seed 42` against the live
service (Cloud Shell → us-central1), first revision `food-on-the-fly-api-00001-bv5`:

| Metric | Value |
| --- | --- |
| Requests | 600 at 10 req/s |
| Success | 600 / 600 (100%) |
| Latency p50 / p95 / p99 | 32.4 / 38.7 / 50.5 ms |
| Latency min / max | 28.4 / 140.2 ms |

**Scaling.** One XGBoost prediction is a few milliseconds, so a single 1 vCPU
instance absorbed 10 req/s without errors and with p99 under 51 ms. The max of
140 ms was a single outlier. With `--min-instances 0` the service scales to
zero when idle, so the first request after a quiet period also pays a cold
start (container start plus loading the pipeline). Set `--min-instances 1` if
that matters, at the cost of an always-on instance. `--max-instances 2` caps
both throughput and cost.

## 8. Monitoring and logs

- **Metrics:** Cloud Console → Cloud Run → `food-on-the-fly-api` → **Metrics**
  shows request count, request latency (p50/p95/p99), container instance
  count, CPU and memory. These are collected automatically.
- **Logs:** the API logs to stdout, which Cloud Run ships to Cloud Logging.
  Logs Explorer query:

  ```
  resource.type="cloud_run_revision"
  resource.labels.service_name="food-on-the-fly-api"
  ```

  Failed predictions are logged at `ERROR` with a full traceback
  (`api/main.py`), so `severity>=ERROR` isolates them.
- **Cost:** budget alert at $10 on the billing account (50/90/100%).

## 9. Rollback

Every deploy creates a new revision; old ones stay available.

```bash
gcloud run revisions list --service food-on-the-fly-api --region us-central1
gcloud run services update-traffic food-on-the-fly-api --region us-central1 \
  --to-revisions <previous-revision>=100
```

Or redeploy an older image tag with the manual command in section 4.

## 10. Options not used

- **Cloud Functions:** the model needs scikit-learn, XGBoost and the custom
  transformers at fixed versions. A container gives the same image in CI, on
  a laptop and in production, so Cloud Run was the better fit.
- **Vertex AI / Compute Engine training:** training takes under a second on
  CPU and runs in the CML job on every PR, so dedicated cloud training was not
  needed.
- **Hugging Face Spaces:** a Gradio app (`app/app.py`) and workflow
  (`.github/workflows/deploy-hf.yml`) exist but were not deployed.

## 11. Troubleshooting

| Problem | Fix |
| --- | --- |
| `exec format error` on Cloud Run | Image built on Apple Silicon (arm64). Build with `--platform linux/amd64` or in Cloud Shell/CI |
| `allUsers` binding rejected | Organization policy `iam.allowedPolicyMemberDomains`. Override it on the project, or keep the service private and call it with `gcloud run services proxy` |
| CI: `Permission 'iam.serviceAccounts.getAccessToken' denied` | The WIF provider only trusts `amomin1993/food_on_the_fly`. Check the repo name in the provider's attribute condition and the `GCP_WIF_PROVIDER` secret |
| `/predict` returns 503 | No model loaded. Check the startup log line `Model ready:` and that `MODEL_PATH` points at a file inside the image |
| Slow first request | Cold start with `--min-instances 0`; see section 7 |

Cleanup: [CLEANUP.md](CLEANUP.md).
