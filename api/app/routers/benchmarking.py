from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.benchmarking import (
    DISCLAIMER, auto_detect_industry, compare_against_industry,
    get_available_industries, get_profile, get_regions,
)

router = APIRouter()


class Ratio(BaseModel):
    ratio_name: str = Field(min_length=1)
    value: float
    unit: str | None = None


class BenchmarkRequest(BaseModel):
    company_name: str = ""
    ratios: list[Ratio] = Field(max_length=100)
    industry_id: str | None = None  # if omitted, guessed from the company name
    region: str = "IN"


@router.get("/industries")
async def list_industries():
    """Sector profiles and regions. All benchmark ranges are illustrative."""
    return {
        "industries": get_available_industries(),
        "regions": get_regions(),
        "illustrative": True,
        "disclaimer": DISCLAIMER,
    }


@router.get("/profile")
async def profile(industry_id: str, region: str = "IN"):
    """The illustrative quartile ranges for one sector in one region."""
    try:
        return get_profile(industry_id, region)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/compare")
async def compare(request: BenchmarkRequest):
    """Compare company ratios with an illustrative sector profile."""
    ratios = [ratio.model_dump() for ratio in request.ratios]
    industry_id = request.industry_id or auto_detect_industry(request.company_name, ratios)
    if not industry_id:
        raise HTTPException(status_code=422, detail="Select a sector: none could be inferred from the company name")
    try:
        return compare_against_industry(ratios, industry_id, request.region)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/auto-detect")
async def auto_detect_endpoint(request: BenchmarkRequest):
    """Guess the sector from the company name (keyword match only)."""
    industry_id = auto_detect_industry(request.company_name, [])
    name = next((s["name"] for s in get_available_industries() if s["id"] == industry_id), None)
    return {"industry_id": industry_id, "name": name, "matched": industry_id is not None}
