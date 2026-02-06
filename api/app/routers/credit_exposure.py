from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.credit_exposure import review_book, sample_book

router = APIRouter()


class Position(BaseModel):
    counterparty: str = Field(min_length=1)
    current_mtm: float
    previous_mtm: float
    collateral: float = Field(ge=0)
    previous_collateral: float = Field(ge=0)
    credit_limit: float = Field(gt=0)
    required_margin: float = Field(ge=0)
    previous_required_margin: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, max_length=8)
    country: Optional[str] = Field(default=None, max_length=60)
    client_type: Optional[str] = Field(default=None, max_length=60)


class ExposureReviewRequest(BaseModel):
    positions: list[Position] = Field(min_length=1, max_length=500)
    reporting_currency: Optional[str] = Field(default=None, max_length=8)
    fx_rates: Optional[dict[str, float]] = None


@router.post("/review")
async def review(req: ExposureReviewRequest):
    """Row-level review, portfolio summary and breach investigation list."""
    try:
        return review_book(
            [position.model_dump() for position in req.positions],
            reporting_currency=req.reporting_currency,
            fx_rates=req.fx_rates,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/sample-book")
async def get_sample_book():
    """Illustrative book of fictional clients across India, China, Japan and South Korea."""
    return sample_book()
