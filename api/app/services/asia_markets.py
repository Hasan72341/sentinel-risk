"""Live market data for India, China, Japan and South Korea.

Prices come from Yahoo Finance's public chart endpoint. It is an unofficial,
unauthenticated source: it can be rate limited, delayed or changed without
notice. When a request fails the functions return a "live data unavailable"
status with the error. They never substitute invented prices.
"""

import asyncio
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from app.services.regional import all_indices, fx_pairs

CHART_HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
CHART_PATH = "/v8/finance/chart/"
SOURCE = "Yahoo Finance public chart endpoint (unofficial; may be delayed)"
UNAVAILABLE_MESSAGE = "Live data unavailable"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
TIMEOUT_SECONDS = 10.0
CACHE_TTL_SECONDS = 60.0
MAX_CONCURRENT_REQUESTS = 4

# Yahoo range -> allowed bar interval for that range.
RANGES = {"5d": "1d", "1mo": "1d", "3mo": "1d", "6mo": "1d", "1y": "1d", "2y": "1wk", "5y": "1wk"}
BOARD_RANGE = "5d"

_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.^=\-]{1,20}$")
_cache: dict[tuple[str, str, str], tuple[float, dict]] = {}


class MarketDataError(Exception):
    """The upstream source did not return usable data."""


def clear_cache() -> None:
    _cache.clear()


def normalize_symbol(symbol: str) -> str:
    """Validate a user-entered ticker (for example RELIANCE.NS, 7203.T, ^N225)."""
    cleaned = str(symbol).strip().upper()
    if not _SYMBOL_RE.match(cleaned):
        raise ValueError(
            "Ticker may contain only letters, digits and . ^ = - (max 20 characters)"
        )
    return cleaned


def _new_client() -> httpx.AsyncClient:
    """HTTP client factory. Tests replace this with a mock transport."""
    return httpx.AsyncClient(
        timeout=TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        follow_redirects=True,
    )


def _iso(timestamp) -> str | None:
    if not isinstance(timestamp, (int, float)):
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if number == number and abs(number) != float("inf") else None


def parse_chart(payload: dict, interval: str = "1d") -> dict:
    """Turn a Yahoo chart payload into a quote plus price history.

    The change fields are day-on-day, so they are only derived from daily bars.
    For any other bar interval they are returned as None and the caller fills
    them from a separate daily request.

    The previous close is the last completed bar before the latest one in the
    series. Yahoo's ``chartPreviousClose`` is the close before the start of the
    requested range, so it is only used when the series has a single bar.
    """
    chart = payload.get("chart") if isinstance(payload, dict) else None
    if not isinstance(chart, dict):
        raise MarketDataError("Unexpected response format")
    error = chart.get("error")
    if error:
        description = error.get("description") if isinstance(error, dict) else str(error)
        raise MarketDataError(description or "Source returned an error")
    results = chart.get("result")
    if not results:
        raise MarketDataError("No data returned for this symbol")

    result = results[0]
    meta = result.get("meta") or {}
    timestamps = result.get("timestamp") or []
    quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0] or {}
    series = {key: quotes.get(key) or [] for key in ("open", "high", "low", "close", "volume")}

    history = []
    for i, stamp in enumerate(timestamps):
        close = _number(series["close"][i]) if i < len(series["close"]) else None
        if close is None:
            continue
        bar = {"date": _iso(stamp)[:10], "timestamp": stamp, "close": close}
        for key in ("open", "high", "low", "volume"):
            bar[key] = _number(series[key][i]) if i < len(series[key]) else None
        history.append(bar)

    price = _number(meta.get("regularMarketPrice"))
    if price is None and history:
        price = history[-1]["close"]
    if price is None:
        raise MarketDataError("No price in response")

    if interval != "1d":
        previous_close = None
    elif len(history) >= 2:
        previous_close = history[-2]["close"]
    else:
        previous_close = _number(meta.get("previousClose")) or _number(meta.get("chartPreviousClose"))

    change = change_pct = None
    if previous_close:
        change = price - previous_close
        change_pct = change / previous_close * 100

    return {
        "symbol": meta.get("symbol"),
        "name": meta.get("longName") or meta.get("shortName") or meta.get("symbol"),
        "currency": meta.get("currency"),
        "exchange": meta.get("fullExchangeName") or meta.get("exchangeName"),
        "instrument_type": meta.get("instrumentType"),
        "timezone": meta.get("exchangeTimezoneName"),
        "price": price,
        "previous_close": previous_close,
        "change": None if change is None else round(change, 6),
        "change_pct": None if change_pct is None else round(change_pct, 4),
        "day_high": _number(meta.get("regularMarketDayHigh")),
        "day_low": _number(meta.get("regularMarketDayLow")),
        "fifty_two_week_high": _number(meta.get("fiftyTwoWeekHigh")),
        "fifty_two_week_low": _number(meta.get("fiftyTwoWeekLow")),
        "volume": _number(meta.get("regularMarketVolume")),
        "as_of": _iso(meta.get("regularMarketTime")),
        "history": history,
    }


async def _fetch_chart(client: httpx.AsyncClient, symbol: str, range_: str, interval: str) -> dict:
    """Fetch and parse one symbol, trying each host once. Raises MarketDataError."""
    key = (symbol, range_, interval)
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    last_error = "No response"
    for host in CHART_HOSTS:
        url = f"https://{host}{CHART_PATH}{quote(symbol, safe='')}"
        try:
            response = await client.get(url, params={"range": range_, "interval": interval})
        except httpx.TimeoutException:
            last_error = "Request timed out"
            continue
        except httpx.HTTPError as exc:
            last_error = f"Network error: {type(exc).__name__}"
            continue

        if response.status_code == 429:
            last_error = "Rate limited by the data source (HTTP 429)"
            continue
        try:
            payload = response.json()
        except ValueError:
            last_error = f"Unreadable response (HTTP {response.status_code})"
            continue
        try:
            parsed = parse_chart(payload, interval)
        except MarketDataError as exc:
            # A well-formed error (unknown symbol, no data) is final: do not retry.
            raise MarketDataError(str(exc)) from exc
        _cache[key] = (time.monotonic(), parsed)
        return parsed
    raise MarketDataError(last_error)


def _unavailable(error: str, **extra) -> dict:
    return {"status": "unavailable", "message": UNAVAILABLE_MESSAGE, "error": error, **extra}


async def _fetch_many(items: list[dict]) -> list[dict]:
    """Quote every item ({symbol, ...}); each row carries its own status."""
    limit = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async def one(client: httpx.AsyncClient, item: dict) -> dict:
        async with limit:
            try:
                parsed = await _fetch_chart(client, item["symbol"], BOARD_RANGE, RANGES[BOARD_RANGE])
            except MarketDataError as exc:
                return {**item, **_unavailable(str(exc))}
            except Exception as exc:  # never let one symbol break the board
                return {**item, **_unavailable(f"Unexpected error: {type(exc).__name__}")}
        quote_fields = {k: v for k, v in parsed.items() if k not in ("history", "symbol", "name")}
        return {**item, "status": "live", **quote_fields,
                "sparkline": [bar["close"] for bar in parsed["history"]]}

    async with _new_client() as client:
        return list(await asyncio.gather(*(one(client, item) for item in items)))


def _board(rows: list[dict], key: str) -> dict:
    live = sum(1 for row in rows if row["status"] == "live")
    status = "live" if live == len(rows) else "partial" if live else "unavailable"
    board = {
        "status": status,
        "source": SOURCE,
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "live_count": live,
        "total_count": len(rows),
        key: rows,
    }
    if status != "live":
        board["message"] = UNAVAILABLE_MESSAGE if not live else "Some live data unavailable"
        board["error"] = next(row["error"] for row in rows if row["status"] != "live")
    return board


async def get_index_board() -> dict:
    """Benchmark indices for the four countries (plus Hang Seng as optional)."""
    return _board(await _fetch_many(all_indices()), "indices")


async def get_fx_board() -> dict:
    """USD against INR, CNY, JPY and KRW, quoted as local units per 1 USD."""
    return _board(await _fetch_many(fx_pairs()), "rates")


async def get_quote(symbol: str, range_: str = "6mo") -> dict:
    """Quote and price history for a user-entered ticker.

    Raises ValueError for an invalid ticker or range. Upstream failures are
    returned as status "unavailable".
    """
    ticker = normalize_symbol(symbol)
    if range_ not in RANGES:
        raise ValueError(f"range must be one of: {', '.join(RANGES)}")
    base = {"symbol": ticker, "range": range_, "interval": RANGES[range_], "source": SOURCE}
    try:
        async with _new_client() as client:
            parsed = await _fetch_chart(client, ticker, range_, RANGES[range_])
            if RANGES[range_] != "1d":
                # Weekly bars cannot give a day-on-day change; take it from daily bars.
                try:
                    daily = await _fetch_chart(client, ticker, BOARD_RANGE, RANGES[BOARD_RANGE])
                    parsed = {**parsed, **{k: daily[k] for k in ("previous_close", "change", "change_pct")}}
                except MarketDataError:
                    pass  # history is still shown; the change fields stay None
    except MarketDataError as exc:
        return {**base, **_unavailable(str(exc))}
    except Exception as exc:
        return {**base, **_unavailable(f"Unexpected error: {type(exc).__name__}")}
    return {**base, "status": "live", **{k: v for k, v in parsed.items() if k != "symbol"},
            "source_symbol": parsed["symbol"]}
