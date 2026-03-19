"""The causal inference demo must serialise to valid JSON."""
import json
import math

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import causal_inference
from app.routers.causal_inference import _json_safe


def test_json_safe_replaces_non_finite_floats_only():
    raw = {"a": float("nan"), "b": [1.5, float("inf"), (2, float("-inf"))], "c": "nan", "d": 0.0}
    assert _json_safe(raw) == {"a": None, "b": [1.5, None, [2, None]], "c": "nan", "d": 0.0}


def test_demo_endpoint_returns_valid_json_with_sample_names():
    app = FastAPI()
    app.include_router(causal_inference.router, prefix="/causal-inference")
    response = TestClient(app).get("/causal-inference/demo")
    assert response.status_code == 200
    body = response.json()
    json.dumps(body, allow_nan=False)
    names = body["summary"]["variable_names"]
    assert names == ["PetroBank", "OilTech", "LotusBank", "Oil Price", "USD/INR FX", "Interest Rate"]
    diagonal = body["granger_causality"]["causality_pvalues"][0][0]
    assert diagonal is None or math.isfinite(diagonal)
