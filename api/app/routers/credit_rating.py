from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.credit_rating import (
    assess_due_diligence,
    due_diligence_checklist,
    generate_credit_review,
    methodology,
    sample_counterparties,
    sample_peers,
    score_counterparty,
)

router = APIRouter()

CounterpartyType = Literal["corporate", "financial_institution", "fund"]
Country = Literal["IN", "CN", "JP", "KR"]


class Qualitative(BaseModel):
    business_profile: int = Field(ge=1, le=5)
    management_governance: int = Field(ge=1, le=5)
    sector_outlook: int = Field(ge=1, le=5)
    country: int = Field(ge=1, le=5)


class Peer(BaseModel):
    name: str = Field(min_length=1)
    country: str | None = None
    sector: str | None = None
    financials: dict[str, float]
    qualitative: Qualitative


class ScoreRequest(BaseModel):
    counterparty_type: CounterpartyType
    name: str = Field(min_length=1, max_length=200)
    country: Country
    sector: str = Field(default="", max_length=100)
    financials: dict[str, float]
    qualitative: Qualitative
    peers: list[Peer] = Field(default_factory=list, max_length=50)
    use_sample_peers: bool = False


class DueDiligenceRequest(BaseModel):
    counterparty_type: CounterpartyType
    country: Country
    states: dict[str, str] = Field(default_factory=dict)


def _score(req: ScoreRequest) -> dict:
    peers = [peer.model_dump() for peer in req.peers]
    if not peers and req.use_sample_peers:
        peers = sample_peers(req.counterparty_type, exclude_name=req.name.strip())
    return score_counterparty(
        req.counterparty_type, req.name, req.country, req.financials,
        req.qualitative.model_dump(), sector=req.sector, peers=peers,
    )


@router.get("/methodology")
async def get_methodology():
    return methodology()


@router.get("/samples")
async def get_samples():
    return sample_counterparties()


@router.post("/score")
async def score(req: ScoreRequest):
    try:
        return _score(req)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/review")
async def review(req: ScoreRequest):
    try:
        scorecard = _score(req)
        return {"scorecard": scorecard, "review": generate_credit_review(scorecard)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/due-diligence")
async def get_due_diligence(counterparty_type: CounterpartyType, country: Country):
    return due_diligence_checklist(counterparty_type, country)


@router.post("/due-diligence/assess")
async def assess(req: DueDiligenceRequest):
    try:
        return assess_due_diligence(req.counterparty_type, req.country, req.states)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
