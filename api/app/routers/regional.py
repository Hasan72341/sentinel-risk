from fastapi import APIRouter, HTTPException

from app.services.regional import (
    REPORTING_CURRENCY, all_market_status, fx_pairs, get_country,
    list_countries, market_status,
)

router = APIRouter()


@router.get("/countries")
async def countries():
    """Reference data for India, China, Japan and South Korea."""
    return {"reporting_currency": REPORTING_CURRENCY, "countries": list_countries(), "fx_pairs": fx_pairs()}


@router.get("/countries/{code}")
async def country(code: str):
    try:
        return get_country(code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/market-status")
async def status_all():
    """Open or closed by regular trading hours (no holiday calendar)."""
    return {"markets": all_market_status()}


@router.get("/market-status/{code}")
async def status_one(code: str):
    try:
        return market_status(code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
