import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.schemas import ReportGenerateRequest

router = APIRouter()

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _load(analysis_id: str, db: Session):
    from app.models.models import AnalysisModel, RatioResultModel

    analysis = db.query(AnalysisModel).filter(AnalysisModel.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    ratios = db.query(RatioResultModel).filter(RatioResultModel.analysis_id == analysis_id).all()
    if not ratios:
        raise HTTPException(status_code=404, detail="No ratio data found for this analysis")
    return analysis, ratios


def _write_pdf(request: ReportGenerateRequest, analysis, ratios) -> str:
    from app.services.report_generator import create_report

    ratio_data = [
        {"category": r.category, "ratio_name": r.ratio_name, "value": r.value,
         "unit": r.unit, "benchmark": r.benchmark, "status": r.status}
        for r in ratios
    ]
    return create_report(
        analysis_id=request.analysis_id,
        company_name=analysis.company_name or "Untitled",
        period=analysis.period or "N/A",
        ratios=ratio_data,
        template=request.template,
        language=request.language,
        include_charts=request.include_charts,
    )


def _write_xlsx(request: ReportGenerateRequest, ratios) -> str:
    import pandas as pd

    rows = [
        {"Category": r.category, "Ratio": r.ratio_name.replace("_", " ").title(), "Value": r.value,
         "Unit": r.unit, "Benchmark": r.benchmark if r.benchmark else "N/A", "Status": r.status}
        for r in ratios
    ]
    output_dir = os.path.join(os.path.expanduser("~"), ".sentinel-risk", "exports")
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, f"analysis_{request.analysis_id[:8]}.xlsx")
    pd.DataFrame(rows).to_excel(file_path, index=False, sheet_name="Financial Ratios")
    return file_path


def _file_response(request: ReportGenerateRequest, fmt: str, db: Session) -> FileResponse:
    from app.models.models import ReportModel

    analysis, ratios = _load(request.analysis_id, db)
    try:
        file_path = _write_pdf(request, analysis, ratios) if fmt == "pdf" else _write_xlsx(request, ratios)
        db.add(ReportModel(analysis_id=request.analysis_id, format=fmt, file_path=file_path,
                           size_bytes=os.path.getsize(file_path)))
        db.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")
    return FileResponse(file_path, media_type=MEDIA_TYPES[fmt], filename=os.path.basename(file_path))


@router.post("/generate")
async def generate_report(request: ReportGenerateRequest, db: Session = Depends(get_db)):
    """Generate a report in the requested format (pdf or xlsx) and return the file."""
    return _file_response(request, request.format, db)


@router.post("/export/xlsx")
async def export_xlsx(request: ReportGenerateRequest, db: Session = Depends(get_db)):
    """Export analysis results to Excel and return the file."""
    return _file_response(request, "xlsx", db)
