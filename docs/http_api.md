# HTTP API Reference

The inference service is a FastAPI app in `src/food_on_the_fly/api/`. It wraps the
trained scikit-learn + XGBoost pipeline and returns an estimated delivery time in
minutes. Interactive docs (Swagger UI) are served at `/docs` and the OpenAPI schema
at `/openapi.json`.

## Running it

```bash
# Local
MODEL_PATH=models/pipeline.joblib uvicorn food_on_the_fly.api.main:app --port 8080

# Docker (same image Cloud Run runs)
docker build -f dockerfiles/Dockerfile.api -t fof-api .
docker run -p 8080:8080 fof-api
```

Set `SERVICE_URL` to `http://localhost:8080` locally, or to the Cloud Run URL
(see `DEPLOYMENT.md`).

## Model loading

Resolved once at startup by `api/model_loader.py`, first match wins:

1. `MODEL_PATH`: local joblib file. The API image sets
   `MODEL_PATH=/app/models/pipeline.joblib`.
2. `MODEL_URI`: any MLflow URI (`runs:/<id>/model`, `models:/<name>/<stage>`, `gs://...`).
3. Default `models:/food_on_the_fly/Staging`.

If no model loads, the service still starts. `/health` reports
`model_loaded: false` and `/predict` returns 503, so a bad deploy is visible
instead of crash-looping.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Service banner with links |
| GET | `/health` | Liveness probe, always 200, reports whether the model is loaded |
| POST | `/predict` | Score one order |
| POST | `/predict/batch` | Score many orders in one call |

### Request schema (`DeliveryRequest`)

Field names match the raw Zomato columns, so the payload goes straight into the
pipeline without renaming.

| Field | Type | Notes |
| --- | --- | --- |
| `Delivery_person_Age` | float | Courier age in years |
| `Delivery_person_Ratings` | float | 0 to 5 |
| `Restaurant_latitude`, `Restaurant_longitude` | float | Degrees |
| `Delivery_location_latitude`, `Delivery_location_longitude` | float | Degrees |
| `Order_Date` | string | Day-first, `19-03-2022` |
| `Time_Orderd` | string | `HH:MM`, 24h (column name keeps the dataset's spelling) |
| `Weather_conditions` | string | Sunny, Cloudy, Fog, Windy, Stormy, Sandstorms |
| `Road_traffic_density` | string | Low, Medium, High, Jam |
| `Vehicle_condition` | int | 0 to 3 |
| `Type_of_order` | string | Snack, Meal, Drinks, Buffet |
| `Type_of_vehicle` | string | motorcycle, scooter, electric_scooter, bicycle |
| `multiple_deliveries` | float | Concurrent deliveries on the trip |
| `Festival` | string | Yes or No |
| `City` | string | Urban, Metropolitian, Semi-Urban |

Unknown category values do not fail. The pipeline's `OneHotEncoder` uses
`handle_unknown="ignore"`, so an unseen value is encoded as all zeros.

## Examples

All responses below are real outputs from the committed `models/pipeline.joblib`.

### Health

```bash
curl -s "$SERVICE_URL/health"
```

```json
{"status": "ok", "model_loaded": true, "model_version": "pipeline.joblib"}
```

### Single prediction

```bash
curl -s -X POST "$SERVICE_URL/predict" \
  -H "Content-Type: application/json" \
  -d '{
    "Delivery_person_Age": 30.0, "Delivery_person_Ratings": 4.5,
    "Restaurant_latitude": 22.745049, "Restaurant_longitude": 75.892471,
    "Delivery_location_latitude": 22.765049, "Delivery_location_longitude": 75.912471,
    "Order_Date": "19-03-2022", "Time_Orderd": "17:30",
    "Weather_conditions": "Sunny", "Road_traffic_density": "Low",
    "Vehicle_condition": 2, "Type_of_order": "Snack", "Type_of_vehicle": "motorcycle",
    "multiple_deliveries": 0.0, "Festival": "No", "City": "Urban"
  }'
```

```json
{"predicted_time_min": 17.52, "model_version": "pipeline.joblib"}
```

### Batch prediction

Same order twice, the second one in a traffic jam during a storm:

```python
import httpx

order = {...}  # same body as above
resp = httpx.post(
    f"{SERVICE_URL}/predict/batch",
    json={
        "instances": [
            order,
            {**order, "Road_traffic_density": "Jam", "Weather_conditions": "Stormy"},
        ]
    },
)
print(resp.json())
```

```json
{"predictions": [17.52, 26.22], "model_version": "pipeline.joblib", "count": 2}
```

## Errors

| Status | When | Body |
| --- | --- | --- |
| 422 | Missing field or wrong type (Pydantic validation) | `{"detail": [{"type": "missing", "loc": ["body", "Delivery_person_Ratings"], "msg": "Field required", ...}]}` |
| 422 | Empty batch | `{"detail": [{"type": "too_short", "loc": ["body", "instances"], "msg": "List should have at least 1 item after validation, not 0", ...}]}` |
| 400 | Payload validates but the pipeline raises (for example an unparseable `Order_Date`) | `{"detail": "Prediction failed: <reason>"}` |
| 503 | No model loaded | `{"detail": "Model is not loaded. Check MODEL_URI/MODEL_PATH configuration."}` |

## Tests

`tests/test_api.py` uses FastAPI's `TestClient` with a stub model to cover
`/health` with no model loaded, single and batch prediction, and clamping of
negative predictions to zero.
