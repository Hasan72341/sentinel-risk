from fastapi import APIRouter, HTTPException, Query

from app.services.asia_markets import RANGES, get_fx_board, get_index_board, get_quote

router = APIRouter()


@router.get("/indices")
async def indices():
    """Benchmark indices for India, China, Japan and South Korea."""
    return await get_index_board()


@router.get("/fx")
async def fx():
    """USD rates for INR, CNY, JPY and KRW."""
    return await get_fx_board()


@router.get("/quote")
async def quote(
    symbol: str = Query(..., min_length=1, max_length=20),
    range: str = Query("6mo"),
):
    """Quote and history for a ticker in Yahoo notation (for example 7203.T)."""
    try:
        return await get_quote(symbol, range)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/ranges")
async def ranges():
    return {"ranges": [{"range": key, "interval": value} for key, value in RANGES.items()]}
