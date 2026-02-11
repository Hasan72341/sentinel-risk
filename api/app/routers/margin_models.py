from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.margin_models import (
    analyze_market_data, backtest_im, calculate_im, calibration_comparison,
    list_sample_series, sample_series, simulate_pfe,
)

router = APIRouter()

Product = Literal["equity", "bond", "irs", "cds", "equity_option", "fx"]
Series = list[float]


class MarginPosition(BaseModel):
    product: Product = "equity"
    side: Optional[str] = None
    notional: float = Field(gt=0)
    label: Optional[str] = Field(default=None, max_length=80)
    duration: Optional[float] = Field(default=None, gt=0)
    strike: Optional[float] = Field(default=None, gt=0)
    expiry_years: Optional[float] = Field(default=None, gt=0)
    volatility: Optional[float] = Field(default=None, gt=0)
    rate: Optional[float] = None
    option_type: Literal["call", "put"] = "call"


class PortfolioPosition(MarginPosition):
    series: Series = Field(min_length=3, max_length=10000)


class MarketDataRequest(BaseModel):
    series: Series = Field(min_length=3, max_length=10000)
    kind: Literal["price", "rate"] = "price"
    window: int = Field(default=20, ge=2, le=1000)


class InitialMarginRequest(BaseModel):
    positions: list[PortfolioPosition] = Field(min_length=1, max_length=50)
    mpor_days: int = Field(default=10, ge=1, le=60)
    confidence: float = Field(default=0.99, gt=0.5, lt=1)
    lookback: Optional[int] = Field(default=None, ge=2)


class CalibrationRequest(BaseModel):
    position: MarginPosition
    series: Series = Field(min_length=3, max_length=10000)
    mpor_days: int = Field(default=10, ge=1, le=60)
    confidence: float = Field(default=0.99, gt=0.5, lt=1)
    lookbacks: list[int] = Field(default=[125, 250, 500], max_length=10)
    ewma_lambda: float = Field(default=0.94, gt=0, lt=1)
    stress_window: int = Field(default=250, ge=2)


class BacktestRequest(BaseModel):
    position: MarginPosition
    series: Series = Field(min_length=3, max_length=10000)
    mpor_days: int = Field(default=10, ge=1, le=60)
    confidence: float = Field(default=0.99, gt=0.5, lt=1)
    lookback: int = Field(default=250, ge=2)
    method: Literal["historical", "parametric"] = "historical"
    non_overlapping: bool = False


class PFERequest(BaseModel):
    product: Product = "irs"
    params: dict[str, Optional[float | str]] = Field(default_factory=dict)
    horizon_years: Optional[float] = Field(default=None, gt=0, le=50)
    quantile: float = Field(default=0.95, ge=0.5, lt=1)
    paths: int = Field(default=5000, ge=100, le=50000)
    seed: Optional[int] = Field(default=None, ge=0)
    mpor_days: int = Field(default=10, ge=1, le=60)
    threshold: float = Field(default=0.0, ge=0)
    initial_margin: float = Field(default=0.0, ge=0)


def _run(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/market-data/analyze")
async def market_data(req: MarketDataRequest):
    """Returns, rolling volatility and worst 1/5/10-day moves of a historical series."""
    return _run(analyze_market_data, req.series, req.kind, req.window)


@router.post("/initial-margin")
async def initial_margin(req: InitialMarginRequest):
    """Historical-simulation and parametric IM per position and for the portfolio (simplified)."""
    positions = [position.model_dump(exclude_none=True) for position in req.positions]
    return _run(calculate_im, positions, req.mpor_days, req.confidence, req.lookback)


@router.post("/initial-margin/calibration")
async def calibration(req: CalibrationRequest):
    """IM for one position under different look-back, EWMA and stressed-period calibrations."""
    return _run(calibration_comparison, req.position.model_dump(exclude_none=True), req.series, req.mpor_days,
                req.confidence, req.lookbacks, req.ewma_lambda, req.stress_window)


@router.post("/initial-margin/backtest")
async def backtest(req: BacktestRequest):
    """How often realised MPOR losses exceeded the rolling IM."""
    return _run(backtest_im, req.position.model_dump(exclude_none=True), req.series, req.mpor_days,
                req.confidence, req.lookback, req.method, req.non_overlapping)


@router.post("/pfe")
async def pfe(req: PFERequest):
    """Expected exposure and PFE profile for one trade, with and without collateral (simplified)."""
    return _run(simulate_pfe, req.product, req.params, req.horizon_years, req.quantile, req.paths,
                req.seed, req.mpor_days, req.threshold, req.initial_margin)


@router.get("/sample-series")
async def sample_series_list():
    """Names of the bundled synthetic series (not market data)."""
    return {"series": list_sample_series()}


@router.get("/sample-series/{name}")
async def sample_series_detail(name: str, observations: int = 750):
    """One synthetic, seeded series for demonstration (not market data)."""
    try:
        return sample_series(name, observations)
    except ValueError as exc:
        raise HTTPException(status_code=404 if "unknown" in str(exc) else 422, detail=str(exc)) from exc
