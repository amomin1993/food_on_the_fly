#!/usr/bin/env bash
# One-time GCP setup and first deploy for Food on the Fly.
# Run from the repo root in Cloud Shell:  bash scripts/gcp_setup.sh
#
# Creates (idempotent, safe to re-run):
#   - Artifact Registry Docker repo for the API image
#   - GCS bucket holding the raw dataset (read by CML in CI)
#   - Runtime service account for the API (no roles needed: model is baked in)
#   - Deployer service account + Workload Identity Federation for GitHub Actions
#   - Cloud Run service (min 0 / max 2 instances, 1 vCPU, 1 GiB)
# Then smoke-tests the live service and prints the values for GitHub secrets.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-food-on-the-fly}"
REGION="${REGION:-us-central1}"
AR_REPO="${AR_REPO:-food-on-the-fly}"
SERVICE="${SERVICE:-food-on-the-fly-api}"
BUCKET="${BUCKET:-food-on-the-fly-data-amomin}"
GH_REPO="${GH_REPO:-amomin1993/food_on_the_fly}"
SA_NAME="github-deployer"
POOL="github"
PROVIDER="github-oidc"
DATA_FILE="${DATA_FILE:-data/raw/zomato_dataset.csv}"

say() { printf '\n==> %s\n' "$*"; }

gcloud config set project "$PROJECT_ID" >/dev/null
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
RUNTIME_SA="fof-api-runtime@${PROJECT_ID}.iam.gserviceaccount.com"

say "Enabling APIs"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com iamcredentials.googleapis.com sts.googleapis.com \
  logging.googleapis.com monitoring.googleapis.com storage.googleapis.com

say "Artifact Registry repo: ${AR_REPO}"
gcloud artifacts repositories describe "$AR_REPO" --location="$REGION" >/dev/null 2>&1 \
  || gcloud artifacts repositories create "$AR_REPO" --repository-format=docker \
       --location="$REGION" --description="Food on the Fly API images"

say "Dataset bucket: gs://${BUCKET}"
gcloud storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1 \
  || gcloud storage buckets create "gs://${BUCKET}" --location="$REGION" \
       --uniform-bucket-level-access
if [[ -f "$DATA_FILE" ]]; then
  gcloud storage cp "$DATA_FILE" "gs://${BUCKET}/data/raw/zomato_dataset.csv"
else
  echo "WARNING: ${DATA_FILE} not found; upload it later with:"
  echo "  gcloud storage cp <path>/zomato_dataset.csv gs://${BUCKET}/data/raw/zomato_dataset.csv"
fi

say "Runtime service account for the API: ${RUNTIME_SA}"
gcloud iam service-accounts describe "$RUNTIME_SA" >/dev/null 2>&1 \
  || gcloud iam service-accounts create fof-api-runtime --display-name="Food on the Fly API runtime"

say "Deployer service account: ${SA_EMAIL}"
gcloud iam service-accounts describe "$SA_EMAIL" >/dev/null 2>&1 \
  || gcloud iam service-accounts create "$SA_NAME" --display-name="GitHub Actions deployer"
for role in roles/run.admin roles/artifactregistry.writer; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" --role="$role" --condition=None >/dev/null
done
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
  --member="serviceAccount:${SA_EMAIL}" --role=roles/iam.serviceAccountUser >/dev/null
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${SA_EMAIL}" --role=roles/storage.objectViewer >/dev/null

say "Workload Identity Federation for ${GH_REPO}"
gcloud iam workload-identity-pools describe "$POOL" --location=global >/dev/null 2>&1 \
  || gcloud iam workload-identity-pools create "$POOL" --location=global \
       --display-name="GitHub Actions"
gcloud iam workload-identity-pools providers describe "$PROVIDER" --location=global \
  --workload-identity-pool="$POOL" >/dev/null 2>&1 \
  || gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
       --location=global --workload-identity-pool="$POOL" \
       --display-name="GitHub OIDC" \
       --issuer-uri="https://token.actions.githubusercontent.com" \
       --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
       --attribute-condition="assertion.repository=='${GH_REPO}'"
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/attribute.repository/${GH_REPO}" \
  >/dev/null

say "Building and pushing the API image"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/api:$(git rev-parse --short HEAD)"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
docker build -t "$IMAGE" -f dockerfiles/Dockerfile.api .
docker push "$IMAGE"

say "Deploying ${SERVICE} to Cloud Run"
gcloud run deploy "$SERVICE" --image="$IMAGE" --region="$REGION" --platform=managed \
  --port=8080 --cpu=1 --memory=1Gi --min-instances=0 --max-instances=2 \
  --service-account="$RUNTIME_SA" \
  --no-allow-unauthenticated

say "Making the service public (allUsers -> run.invoker)"
if ! gcloud run services add-iam-policy-binding "$SERVICE" --region="$REGION" \
      --member=allUsers --role=roles/run.invoker >/dev/null 2>&1; then
  echo "BLOCKED: the organization policy iam.allowedPolicyMemberDomains rejected allUsers."
  echo "Stop here and send this output back; the service is deployed but private."
  exit 2
fi

URL="$(gcloud run services describe "$SERVICE" --region="$REGION" --format='value(status.url)')"

say "Smoke test against ${URL}"
curl -sS "${URL}/health"; echo
curl -sS -X POST "${URL}/predict" -H "Content-Type: application/json" -d '{
  "Delivery_person_Age": 30.0, "Delivery_person_Ratings": 4.5,
  "Restaurant_latitude": 22.745049, "Restaurant_longitude": 75.892471,
  "Delivery_location_latitude": 22.765049, "Delivery_location_longitude": 75.912471,
  "Order_Date": "19-03-2022", "Time_Orderd": "17:30",
  "Weather_conditions": "Sunny", "Road_traffic_density": "Low",
  "Vehicle_condition": 2, "Type_of_order": "Snack", "Type_of_vehicle": "motorcycle",
  "multiple_deliveries": 0.0, "Festival": "No", "City": "Urban"}'; echo

say "Load test: 600 req/min for 60 s"
python3 -m pip install --quiet --user httpx
python3 scripts/load_test.py --url "$URL" --rate 600 --duration 60 --seed 42 \
  | tee load_test_results.txt

say "GitHub Actions secrets (Settings > Secrets and variables > Actions)"
cat <<EOF
GCP_PROJECT_ID      = ${PROJECT_ID}
GCP_REGION          = ${REGION}
GCP_ARTIFACT_REPO   = ${AR_REPO}
GCP_SERVICE_ACCOUNT = ${SA_EMAIL}
GCP_WIF_PROVIDER    = projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/providers/${PROVIDER}
EOF

say "Done. Service URL: ${URL}"
