"""Copy training outputs to Cloud Storage.

Used as the last step of the Vertex AI custom training job, where the
container's filesystem disappears when the job ends.

    python scripts/upload_artifacts.py gs://<bucket>/models/<run-id>
"""

from __future__ import annotations

import sys
from pathlib import Path

import gcsfs

ARTIFACTS = [
    "models/pipeline.joblib",
    "metrics.txt",
    "prediction_scatter.png",
    "residual_plot.png",
    "error_distribution.png",
    "feature_importance.png",
    "logs/food_on_the_fly.log",
]


def main() -> None:
    if len(sys.argv) != 2 or not sys.argv[1].startswith("gs://"):
        raise SystemExit("usage: upload_artifacts.py gs://bucket/prefix")
    dest = sys.argv[1].rstrip("/")
    fs = gcsfs.GCSFileSystem()
    for rel in ARTIFACTS:
        path = Path(rel)
        if not path.exists():
            print(f"skip (missing): {rel}")
            continue
        target = f"{dest}/{path.name}"
        fs.put(str(path), target)
        print(f"uploaded {rel} -> {target}")


if __name__ == "__main__":
    main()
