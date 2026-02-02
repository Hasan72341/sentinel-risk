from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.counterparty_monitor import review_portfolio, sample_portfolio

router = APIRouter()

Grade = Literal["IR1", "IR2", "IR3", "IR4", "IR5", "IR6", "IR7", "IR8", "IR9", "IR10"]


class Counterparty(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    counterparty_type: Literal["corporate", "financial_institution", "fund"]
    country: Literal["IN", "CN", "JP", "KR"]
    rating: Grade
    previous_rating: Grade | None = None
    review_frequency: Literal["annual", "semi_annual"]
    last_review_date: date
    limit: float = Field(gt=0)
    utilisation: float = Field(ge=0)


class PortfolioReviewRequest(BaseModel):
    as_of: date | None = None
    counterparties: list[Counterparty] = Field(min_length=1, max_length=1000)


@router.get("/sample")
async def get_sample(as_of: date | None = None):
    return sample_portfolio(as_of)


@router.post("/review")
async def review(req: PortfolioReviewRequest):
    try:
        return review_portfolio([item.model_dump() for item in req.counterparties], req.as_of)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
