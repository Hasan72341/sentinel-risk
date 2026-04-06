from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.compliance import (
    DEFAULT_TOLERANCE_PCT, DISCLAIMER, DISCLOSURE_ITEMS,
    get_checks, get_compliance_standards, get_frameworks, run_compliance_check,
)

router = APIRouter()


class ComplianceRequest(BaseModel):
    financial_data: dict[str, float | None]
    framework: str = "IFRS"
    prior_period: dict[str, float | None] | None = None
    disclosures: dict[str, bool | None] | None = None
    statements_present: list[str] | None = None
    tolerance_pct: float = Field(default=DEFAULT_TOLERANCE_PCT, ge=0, le=5)


@router.post("/check")
async def run_check(request: ComplianceRequest):
    """Run presentation and consistency checks under the selected framework."""
    try:
        return run_compliance_check(
            request.financial_data,
            framework=request.framework,
            prior_period=request.prior_period,
            disclosures=request.disclosures,
            statements_present=request.statements_present,
            tolerance_pct=request.tolerance_pct,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/frameworks")
async def list_frameworks():
    """Supported accounting frameworks, the check catalogue and checklist items."""
    return {
        "frameworks": get_frameworks(),
        "checks": get_checks(),
        "disclosure_items": [{"id": key, "label": label} for key, label in DISCLOSURE_ITEMS],
        "disclaimer": DISCLAIMER,
    }


@router.get("/standards")
async def list_standards():
    """Check groups (kept for older clients; see /frameworks)."""
    return {"standards": get_compliance_standards()}
