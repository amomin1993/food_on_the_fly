#!/usr/bin/env bash
# Phase 3 extras, run from the repo root in Cloud Shell after gcp_setup.sh:
#   1. Vertex AI custom training job (training image, data from the GCS bucket,
#      artifacts written back to the bucket)
#   2. The model behind a Cloud Function (gen2, HTTP trigger)
# Usage:  bash scripts/gcp_extras.sh 2>&1 | tee ~/gcp_extras_log.txt
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-food-on-the-fly}"
REGION="${REGION:-us-central1}"
AR_REPO="${AR_REPO:-food-on-the-fly}"
BUCKET="${BUCKET:-food-on-the-fly-data-amomin}"
MODEL_CONFIG="${MODEL_CONFIG:-xgboost_optimized}"
TRAINER_SA="fof-trainer@${PROJECT_ID}.iam.gserviceaccount.com"
FUNCTION="${FUNCTION:-fof-predict}"

say() { printf '\n==> %s\n' "$*"; }

gcloud config set project "$PROJECT_ID" >/dev/null
gcloud services enable aiplatform.googleapis.com cloudfunctions.googleapis.com \
  cloudbuild.googleapis.com run.googleapis.com eventarc.googleapis.com

# ---------------------------------------------------------------- Vertex AI
say "Training service account: ${TRAINER_SA}"
gcloud iam service-accounts describe "$TRAINER_SA" >/dev/null 2>&1 \
  || gcloud iam service-accounts create fof-trainer --display-name="Food on the Fly training job"
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${TRAINER_SA}" --role=roles/storage.objectAdmin >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${TRAINER_SA}" --role=roles/logging.logWriter \
  --condition=None >/dev/null

say "Building and pushing the training image (dockerfiles/Dockerfile)"
TRAIN_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/train:$(git rev-parse --short HEAD)"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
docker build -t "$TRAIN_IMAGE" -f dockerfiles/Dockerfile .
docker push "$TRAIN_IMAGE"

RUN_ID="$(date +%Y%m%d-%H%M%S)"
OUT="gs://${BUCKET}/models/${RUN_ID}"
cat > /tmp/vertex_job.yaml <<YAML
workerPoolSpecs:
  - machineSpec:
      machineType: n1-standard-4
    replicaCount: 1
    containerSpec:
      imageUri: ${TRAIN_IMAGE}
      command: ["bash", "-c"]
      args:
        - >-
          python -m food_on_the_fly.data.temporal_split &&
          python -m food_on_the_fly.train_model model=${MODEL_CONFIG} &&
          python scripts/upload_artifacts.py ${OUT}
      env:
        - name: MLFLOW_ALLOW_FILE_STORE
          value: "true"
serviceAccount: ${TRAINER_SA}
YAML

say "Submitting Vertex AI custom job (config: ${MODEL_CONFIG})"
JOB="$(gcloud ai custom-jobs create --region="$REGION" \
  --display-name="fof-train-${MODEL_CONFIG}-${RUN_ID}" \
  --config=/tmp/vertex_job.yaml --format='value(name)')"
echo "Job: ${JOB}"

say "Waiting for the job to finish (usually 5-10 minutes, most of it provisioning)"
while true; do
  STATE="$(gcloud ai custom-jobs describe "$JOB" --region="$REGION" --format='value(state)')"
  echo "$(date +%H:%M:%S) ${STATE}"
  case "$STATE" in
    JOB_STATE_SUCCEEDED) break ;;
    JOB_STATE_FAILED|JOB_STATE_CANCELLED)
      gcloud ai custom-jobs describe "$JOB" --region="$REGION" --format='value(error)'
      echo "Training job did not succeed; continuing with the Cloud Function."
      break ;;
  esac
  sleep 30
done
echo "Artifacts:"
gcloud storage ls "${OUT}/" || true
gcloud storage cat "${OUT}/metrics.txt" || true

# ---------------------------------------------------------- Cloud Functions
say "Build service account for Cloud Functions (new orgs give the default one no roles)"
BUILDER_SA="fof-builder@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud iam service-accounts describe "$BUILDER_SA" >/dev/null 2>&1 \
  || gcloud iam service-accounts create fof-builder --display-name="Food on the Fly function builds"
# A brand new service account can take a minute before IAM will bind it.
for i in 1 2 3 4 5 6; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${BUILDER_SA}" --role=roles/cloudbuild.builds.builder \
    --condition=None >/dev/null && break
  echo "Service account not visible to IAM yet, retrying in 15s ($i/6)"
  sleep 15
done

say "Packaging the Cloud Function"
SRC="$(mktemp -d)"
cp deploy/cloud_function/main.py deploy/cloud_function/requirements.txt "$SRC/"
cp -r src/food_on_the_fly "$SRC/"
cp models/pipeline.joblib "$SRC/"
find "$SRC" -name '__pycache__' -prune -exec rm -rf {} +

say "Deploying Cloud Function ${FUNCTION} (gen2, python311, HTTP)"
gcloud functions deploy "$FUNCTION" --gen2 --region="$REGION" --runtime=python311 \
  --source="$SRC" --entry-point=predict --trigger-http --allow-unauthenticated \
  --memory=1GiB --max-instances=2 \
  --run-service-account="fof-api-runtime@${PROJECT_ID}.iam.gserviceaccount.com" \
  --build-service-account="projects/${PROJECT_ID}/serviceAccounts/${BUILDER_SA}"

FN_URL="$(gcloud functions describe "$FUNCTION" --gen2 --region="$REGION" \
  --format='value(serviceConfig.uri)')"

say "Function smoke test against ${FN_URL}"
curl -sS "$FN_URL"; echo
curl -sS -X POST "$FN_URL" -H "Content-Type: application/json" -d '{
  "Delivery_person_Age": 30.0, "Delivery_person_Ratings": 4.5,
  "Restaurant_latitude": 22.745049, "Restaurant_longitude": 75.892471,
  "Delivery_location_latitude": 22.765049, "Delivery_location_longitude": 75.912471,
  "Order_Date": "19-03-2022", "Time_Orderd": "17:30",
  "Weather_conditions": "Sunny", "Road_traffic_density": "Low",
  "Vehicle_condition": 2, "Type_of_order": "Snack", "Type_of_vehicle": "motorcycle",
  "multiple_deliveries": 0.0, "Festival": "No", "City": "Urban"}'; echo

say "Summary"
echo "Vertex AI job : ${JOB}"
echo "Artifacts     : ${OUT}/"
echo "Function URL  : ${FN_URL}"
