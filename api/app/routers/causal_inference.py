"""Causal inference demo router."""
import math

from fastapi import APIRouter

from app.services.causal_inference import causal_inference_demo

router = APIRouter()


def _json_safe(value):
    """Replace NaN and infinite floats with None so the response is valid JSON.

    Granger matrices leave the diagonal undefined (a series is not tested
    against itself), which the service represents as NaN.
    """
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


@router.get("/demo")
def demo():
    """Run the causal inference demo on simulated, illustrative sample series."""
    return _json_safe(causal_inference_demo())
