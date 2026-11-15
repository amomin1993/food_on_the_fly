#!/usr/bin/env bash
# Creates the Cloud Monitoring dashboard and the 5xx alert policy for the API.
# Run from the repo root in Cloud Shell:
#   NOTIFY_EMAIL=you@example.com bash scripts/gcp_monitoring.sh
# NOTIFY_EMAIL is optional; without it the alert still fires in the console.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-food-on-the-fly}"
gcloud config set project "$PROJECT_ID" >/dev/null

echo "==> Dashboard"
gcloud monitoring dashboards create --config-from-file=deploy/monitoring/dashboard.json

echo "==> Alert policy: 5xx responses"
POLICY_FILE=deploy/monitoring/alert_5xx.json
if [[ -n "${NOTIFY_EMAIL:-}" ]]; then
  CHANNEL="$(gcloud beta monitoring channels create \
    --display-name="Food on the Fly alerts" --type=email \
    --channel-labels=email_address="$NOTIFY_EMAIL" --format='value(name)')"
  python3 - "$CHANNEL" <<'PY'
import json, sys
p = "deploy/monitoring/alert_5xx.json"
policy = json.load(open(p))
policy["notificationChannels"] = [sys.argv[1]]
json.dump(policy, open("/tmp/alert_5xx.json", "w"))
PY
  POLICY_FILE=/tmp/alert_5xx.json
fi
gcloud alpha monitoring policies create --policy-from-file="$POLICY_FILE"

echo "==> Done. Console: Monitoring > Dashboards > 'Food on the Fly API', Monitoring > Alerting"
