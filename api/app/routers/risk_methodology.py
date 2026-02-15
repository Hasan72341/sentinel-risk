from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.risk_methodology import (
    SAMPLE_DISCLAIMER, SAMPLE_PORTFOLIO_NAME, SAMPLE_POSITIONS,
    backtest_sample, backtest_var, list_risk_factors, sample_portfolio,
)
from app.services.risk_methodology_monitoring import (
    model_performance_report, sample_model_performance_report,
)
from app.services.risk_methodology_stress import (
    SAMPLE_CREDIT_EXPOSURES, SCENARIO_BY_ID, SCENARIO_DISCLAIMER,
    reverse_stress_test, run_stress_test, scenario_library, simulate_economic_capital,
)

router = APIRouter()

Method = Literal["historical", "parametric"]


class BacktestRequest(BaseModel):
    """Leave `pnl` empty to use the bundled synthetic sample book."""
    pnl: list[float] | None = Field(default=None, min_length=3, max_length=10_000)
    dates: list[str] | None = None
    factor_pnl: dict[str, list[float]] | None = None
    confidence: float = Field(default=0.99, gt=0.5, lt=1)
    window: int = Field(default=250, ge=2, le=2_000)
    method: Method = "historical"
    es_confidence: float = Field(default=0.975, gt=0.5, lt=1)
    seed: int = Field(default=42, ge=0)
    days: int = Field(default=750, ge=60, le=5_000)


class Position(BaseModel):
    factor_id: str
    sensitivity: float


class CustomScenario(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = ""
    shocks: dict[str, float] = Field(min_length=1)


class StressRequest(BaseModel):
    """Leave `positions` empty to use the bundled sample book."""
    positions: list[Position] | None = Field(default=None, min_length=1, max_length=200)
    scenario_ids: list[str] | None = None
    custom_scenarios: list[CustomScenario] = Field(default_factory=list, max_length=20)


class ReverseStressRequest(BaseModel):
    positions: list[Position] | None = Field(default=None, min_length=1, max_length=200)
    scenario_id: str | None = None
    shocks: dict[str, float] | None = None
    loss_threshold: float = Field(gt=0)


class CreditExposure(BaseModel):
    name: str = Field(min_length=1)
    ead: float = Field(ge=0)
    pd: float = Field(ge=0, le=1)
    lgd: float = Field(ge=0, le=1)


class EconomicCapitalRequest(BaseModel):
    market_annual_vol: float | None = Field(default=None, ge=0)
    credit_exposures: list[CreditExposure] | None = Field(default=None, max_length=200)
    asset_correlation: float = Field(default=0.20, ge=0, lt=1)
    operational_expected_loss: float = Field(default=2_000_000, ge=0)
    operational_sigma: float = Field(default=1.0, gt=0, le=3)
    correlations: dict[str, float] | None = None
    confidence: float = Field(default=0.999, gt=0.5, lt=1)
    simulations: int = Field(default=50_000, ge=1_000, le=200_000)
    seed: int = Field(default=7, ge=0)


def _positions(positions: list[Position] | None) -> list[dict] | None:
    return None if positions is None else [position.model_dump() for position in positions]


@router.get("/sample-portfolio")
async def get_sample_portfolio(seed: int = 42, days: int = Query(default=750, ge=60, le=5_000)):
    try:
        return sample_portfolio(seed, days)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/var-backtest")
async def var_backtest(req: BacktestRequest):
    try:
        if req.pnl is None:
            return backtest_sample(req.seed, req.days, req.confidence, req.window, req.method, req.es_confidence)
        return backtest_var(
            req.pnl, req.dates, req.confidence, req.window, req.method, req.es_confidence, req.factor_pnl
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/model-monitoring")
async def model_monitoring(req: BacktestRequest):
    try:
        if req.pnl is None:
            return sample_model_performance_report(req.seed, req.days, req.confidence, req.window, req.method)
        return model_performance_report(
            req.pnl, req.dates, req.confidence, req.window, req.method, req.factor_pnl
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/stress/scenarios")
async def stress_scenarios():
    return {
        "factors": list_risk_factors(),
        "scenarios": scenario_library(),
        "sample_portfolio": {
            "name": SAMPLE_PORTFOLIO_NAME, "currency": "USD",
            "positions": SAMPLE_POSITIONS, "disclaimer": SAMPLE_DISCLAIMER,
        },
        "disclaimer": SCENARIO_DISCLAIMER,
    }


@router.post("/stress/run")
async def stress_run(req: StressRequest):
    try:
        return run_stress_test(
            _positions(req.positions), req.scenario_ids,
            [scenario.model_dump() for scenario in req.custom_scenarios],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/stress/reverse")
async def stress_reverse(req: ReverseStressRequest):
    try:
        if req.shocks:
            shocks = req.shocks
        elif req.scenario_id in SCENARIO_BY_ID:
            shocks = SCENARIO_BY_ID[req.scenario_id]["shocks"]
        else:
            raise ValueError("provide a known scenario_id or a set of shocks")
        return reverse_stress_test(_positions(req.positions), shocks, req.loss_threshold)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/economic-capital/sample-exposures")
async def economic_capital_sample_exposures():
    return {"exposures": SAMPLE_CREDIT_EXPOSURES, "disclaimer": SAMPLE_DISCLAIMER}


@router.post("/economic-capital")
async def economic_capital(req: EconomicCapitalRequest):
    try:
        exposures = None if req.credit_exposures is None else [e.model_dump() for e in req.credit_exposures]
        return simulate_economic_capital(
            req.market_annual_vol, exposures, req.asset_correlation, req.operational_expected_loss,
            req.operational_sigma, req.correlations, req.confidence, req.simulations, req.seed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
