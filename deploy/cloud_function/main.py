"""Cloud Functions (gen2) entry point for the delivery-time model.

Cloud Functions runs a Flask-style HTTP handler, not an ASGI app, so this
function wraps the same pieces the FastAPI service uses: the Pydantic request
schema from ``food_on_the_fly.api.schemas`` for validation and
``food_on_the_fly.api.model_loader`` for loading and scoring. A request that
works against Cloud Run works here unchanged.

Routes (single function URL):
    GET  /            health check
    POST /            one order (same body as the API's /predict)
    POST /  {"instances": [...]}  batch (same body as /predict/batch)
"""

from __future__ import annotations

import os
from typing import Any

import functions_framework
from pydantic import ValidationError

os.environ.setdefault(
    "MODEL_PATH", os.path.join(os.path.dirname(__file__), "pipeline.joblib")
)

from food_on_the_fly.api import model_loader  # noqa: E402
from food_on_the_fly.api.schemas import (  # noqa: E402
    BatchDeliveryRequest,
    DeliveryRequest,
)

model_loader.try_load()


def _json(body: dict[str, Any], status: int = 200) -> tuple[dict[str, Any], int]:
    return body, status


@functions_framework.http
def predict(request: Any) -> tuple[dict[str, Any], int]:
    if request.method == "GET":
        return _json(
            {
                "status": "ok",
                "model_loaded": model_loader.is_loaded(),
                "model_version": model_loader.model_version(),
                "runtime": "cloud-functions",
            }
        )
    if request.method != "POST":
        return _json({"detail": "Use GET for health or POST to predict."}, 405)
    if not model_loader.is_loaded():
        return _json({"detail": "Model is not loaded."}, 503)

    payload = request.get_json(silent=True)
    if payload is None:
        return _json({"detail": "Body must be JSON."}, 400)

    try:
        if isinstance(payload, dict) and "instances" in payload:
            batch = BatchDeliveryRequest.model_validate(payload)
            rows = [item.model_dump() for item in batch.instances]
            preds = model_loader.predict_frame(rows)
            return _json(
                {
                    "predictions": preds,
                    "model_version": model_loader.model_version(),
                    "count": len(preds),
                }
            )
        single = DeliveryRequest.model_validate(payload)
        pred = model_loader.predict_frame([single.model_dump()])[0]
        return _json(
            {
                "predicted_time_min": pred,
                "model_version": model_loader.model_version(),
            }
        )
    except ValidationError as exc:
        return _json({"detail": exc.errors(include_url=False)}, 422)
    except Exception as exc:  # noqa: BLE001 - surface pipeline errors as 400
        return _json({"detail": f"Prediction failed: {exc}"}, 400)
