"""Model analytics: serves the evaluation artifacts produced by the ML
pipeline. Nothing here is computed at request time - the numbers are
exactly what evaluate.py measured on the held-out test set."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from ..config import settings

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _read(name: str) -> dict | list:
    path = settings.artifact_dir / name
    if not path.exists():
        raise HTTPException(503, f"artifact {name} missing - run the ML "
                                 f"pipeline (riskmodel.train / evaluate)")
    return json.loads(path.read_text())


def _read_optional(name: str):
    path = settings.artifact_dir / name
    return json.loads(path.read_text()) if path.exists() else None


@router.get("")
def analytics():
    thresholds = _read("thresholds.json")
    return {
        "metrics": _read("metrics.json"),
        "model_selection": _read("model_selection.json"),
        "global_importance": _read("global_importance.json"),
        "threshold_curve": thresholds.get("cost_curve", []),
        "robustness": _read_optional("robustness.json"),
        "dataset_manifest": json.loads(
            (settings.data_dir / "manifest.json").read_text())
        if (settings.data_dir / "manifest.json").exists() else None,
    }
