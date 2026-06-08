"""Read-only, reproducible public corporate filings case study."""
import io
import json
from pathlib import Path
import sys
import tempfile
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

SRC_ROOT = Path(__file__).resolve().parents[3] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sentinel_risk.public_filings import build_case, export_case, statement_csv  # noqa: E402

router = APIRouter()


def case_data() -> dict:
    try:
        return build_case()
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=503, detail=f"Public filings cache unavailable or invalid: {exc}") from exc


@router.get("/case")
def get_case():
    return case_data()


@router.get("/export")
def download_case():
    case = case_data()
    buffer = io.BytesIO()
    with tempfile.TemporaryDirectory() as directory:
        export_case(case, Path(directory))
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(Path(directory).iterdir()):
                archive.write(path, path.name)
            archive.writestr("sources.json", json.dumps(case["sources"], indent=2))
    return Response(buffer.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="public-filings-credit-case.zip"'})


@router.get("/{ticker}/statements")
def get_statements(ticker: str):
    issuer = next((issuer for issuer in case_data()["issuers"] if issuer["ticker"] == ticker.upper()), None)
    if issuer is None:
        raise HTTPException(status_code=404, detail="Issuer not in the bundled case")
    return Response(statement_csv(issuer), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{issuer["ticker"]}_statements.csv"'})
