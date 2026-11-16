# Resource Cleanup

Everything for this project lives in the GCP project `food-on-the-fly`, so
the cleanest teardown is deleting the project. The per-resource commands are
below too, for a partial cleanup that keeps the project.

> Keep the Cloud Run service up until grading is finished. It scales to zero
> when idle, so leaving it running costs nothing while nobody calls it.

## What exists and what it costs

| Resource | Name | Cost when idle |
| --- | --- | --- |
| Cloud Run service | `food-on-the-fly-api` (min 0 instances) | none |
| Artifact Registry | `food-on-the-fly` (one image per deploy) | storage beyond the free tier |
| Cloud Storage | `gs://food-on-the-fly-data-amomin` (~6 MB CSV, trained models under `models/`) | negligible |
| Cloud Function | `fof-predict`, deleted 2026-11-15 | none |
| Vertex AI | finished custom jobs (billed only while running) | none |
| Service accounts, WIF pool | `fof-api-runtime`, `github-deployer`, pool `github` (`fof-trainer` and `fof-builder` deleted 2026-11-15) | none |
| Logs and metrics | Cloud Logging / Monitoring defaults | within free allotment |

Images are the only thing that grows: every merge to `main` pushes a new one.

## Routine cleanup: old images

Keep the image the service is running and delete the rest:

```bash
REPO=us-central1-docker.pkg.dev/food-on-the-fly/food-on-the-fly/api
# The service is deployed by tag, so look up the digest the live revision runs.
REV=$(gcloud run services describe food-on-the-fly-api --region us-central1 \
  --format='value(status.latestReadyRevisionName)')
LIVE=$(gcloud run revisions describe "$REV" --region us-central1 \
  --format='value(status.imageDigest)')
echo "Keeping $LIVE"
gcloud artifacts docker images list "$REPO" --include-tags --format='value(version)' \
  | while read -r digest; do
      [[ "$LIVE" == *"$digest"* ]] && continue
      gcloud artifacts docker images delete "$REPO@$digest" --quiet --delete-tags
    done
gcloud artifacts docker images list "$REPO" --include-tags
```

## Cleanup done for the submission

The Hugging Face Space calls the Cloud Run API, so the service and the image it
runs stay up until grading is finished. Everything else that the demo does not
need was removed after the demo was recorded:

```bash
gcloud config set project food-on-the-fly

# Cloud Function (the Vertex AI job and its outputs in the bucket stay as evidence)
gcloud functions delete fof-predict --gen2 --region us-central1 --quiet

# Training image
gcloud artifacts docker images delete \
  us-central1-docker.pkg.dev/food-on-the-fly/food-on-the-fly/train \
  --delete-tags --quiet

# Old API images: run the "Routine cleanup" block above

# Service accounts only the training job and the function used
gcloud iam service-accounts delete fof-trainer@food-on-the-fly.iam.gserviceaccount.com --quiet
gcloud iam service-accounts delete fof-builder@food-on-the-fly.iam.gserviceaccount.com --quiet

# Check: only food-on-the-fly-api should be listed, with one api image
gcloud run services list --region us-central1
gcloud artifacts docker images list us-central1-docker.pkg.dev/food-on-the-fly/food-on-the-fly --include-tags
```

Gen2 Cloud Functions are listed as Cloud Run services, so after this the Cloud
Run page shows only `food-on-the-fly-api`. Screenshot:
`docs/images/phase3/gcp_cleanup.png`. After grading, run the full teardown
below.

## Full teardown

### Option A: delete the project (recommended)

```bash
gcloud projects delete food-on-the-fly
```

This stops all billing for the project at once. Google keeps it recoverable
for 30 days (`gcloud projects undelete food-on-the-fly`), then removes it.

### Option B: delete resources one by one

```bash
gcloud config set project food-on-the-fly
PROJECT_NUMBER=$(gcloud projects describe food-on-the-fly --format='value(projectNumber)')

# Serving
gcloud run services delete food-on-the-fly-api --region us-central1 --quiet
gcloud functions delete fof-predict --gen2 --region us-central1 --quiet

# Images
gcloud artifacts repositories delete food-on-the-fly --location us-central1 --quiet

# Data
gcloud storage rm --recursive gs://food-on-the-fly-data-amomin

# CI identity
gcloud iam workload-identity-pools delete github --location global --quiet
gcloud iam service-accounts delete github-deployer@food-on-the-fly.iam.gserviceaccount.com --quiet
gcloud iam service-accounts delete fof-api-runtime@food-on-the-fly.iam.gserviceaccount.com --quiet
gcloud iam service-accounts delete fof-trainer@food-on-the-fly.iam.gserviceaccount.com --quiet
gcloud iam service-accounts delete fof-builder@food-on-the-fly.iam.gserviceaccount.com --quiet

# APIs (optional once the resources are gone)
gcloud services disable run.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com cloudfunctions.googleapis.com aiplatform.googleapis.com \
  eventarc.googleapis.com --force
```

Then remove the five `GCP_*` secrets from the GitHub repository, or the deploy
and CML workflows will fail on their next run. On Hugging Face, delete the
Space (Settings → Delete this Space) and revoke the `github-deploy` token, then
remove `HF_TOKEN` and `HF_SPACE_ID` from GitHub.

### Verify nothing is left

```bash
gcloud run services list --region us-central1
gcloud functions list --region us-central1
gcloud artifacts repositories list --location us-central1
gcloud storage ls
gcloud iam service-accounts list
```

Each should come back empty, apart from Google-managed default accounts.

## Cost monitoring

- **Budget alert:** Billing → Budgets & alerts, $10/month on the billing
  account, email at 50%, 90% and 100%. "Other savings" is unchecked so the
  free-trial credit does not hide real usage.
- **Where to look:** Billing → Reports, grouped by service. Expected spend for
  this project is a few cents, almost all Artifact Registry storage.
- **Guardrails already in place:** Cloud Run `--min-instances 0` (no idle
  cost) and `--max-instances 2` (a traffic spike cannot scale up costs).
