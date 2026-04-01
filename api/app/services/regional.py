"""Regional reference data for India, China, Japan and South Korea.

Static reference facts used across the app: currency, number grouping,
fiscal-year convention, accounting framework, regulators, exchanges,
benchmark indices (with Yahoo Finance symbols) and regular trading hours.

Market status is derived from regular weekday trading hours only. Exchange
holidays, half days and special sessions are not modelled, so the status is
an indication, not an exchange calendar.
"""

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

REPORTING_CURRENCY = "USD"

MARKET_STATUS_NOTE = (
    "Based on regular weekday trading hours. Exchange holidays, half days and "
    "special sessions are not modelled."
)

# Currency symbols are written as escapes so the source stays ASCII.
COUNTRIES: dict[str, dict] = {
    "IN": {
        "code": "IN",
        "name": "India",
        "currency": {"code": "INR", "name": "Indian rupee", "symbol": "\u20b9", "minor_units": 2},
        "locale": "en-IN",
        "number_grouping": {
            "style": "indian",
            "description": (
                "Indian grouping: the last three digits form one group and the rest are "
                "grouped in twos (for example 12,34,56,789)."
            ),
            "units": [
                {"name": "lakh", "value": 100_000},
                {"name": "crore", "value": 10_000_000},
            ],
        },
        "fiscal_year": {
            "start_month": 4,
            "end_month": 3,
            "description": "1 April to 31 March.",
        },
        "accounting": {
            "primary_framework": "Ind AS",
            "framework_id": "IND_AS",
            "description": (
                "Indian Accounting Standards (Ind AS), converged with IFRS, apply to listed "
                "and larger companies. Statement formats follow Schedule III of the "
                "Companies Act, 2013."
            ),
            "alternatives": [],
        },
        "regulators": [
            {"short_name": "SEBI", "name": "Securities and Exchange Board of India", "role": "Securities markets"},
            {"short_name": "RBI", "name": "Reserve Bank of India", "role": "Central bank and banking supervision"},
            {"short_name": "IRDAI", "name": "Insurance Regulatory and Development Authority of India", "role": "Insurance"},
        ],
        "exchanges": [
            {"short_name": "NSE", "name": "National Stock Exchange of India", "yahoo_suffix": ".NS"},
            {"short_name": "BSE", "name": "BSE (formerly Bombay Stock Exchange)", "yahoo_suffix": ".BO"},
        ],
        "indices": [
            {"name": "Nifty 50", "symbol": "^NSEI"},
            {"name": "Sensex", "symbol": "^BSESN"},
        ],
        "fx_symbol": "INR=X",
        "market": {
            "timezone": "Asia/Kolkata",
            "timezone_label": "IST (UTC+5:30)",
            "sessions": [["09:15", "15:30"]],
            "lunch_break": False,
        },
    },
    "CN": {
        "code": "CN",
        "name": "China",
        "currency": {"code": "CNY", "name": "Chinese yuan renminbi", "symbol": "\u00a5", "minor_units": 2},
        "locale": "en-US",
        "number_grouping": {
            "style": "western",
            "description": (
                "Thousands grouping in English-language reports. Local reports commonly "
                "state amounts in units of ten thousand (wan) or one hundred million (yi)."
            ),
            "units": [
                {"name": "wan", "value": 10_000},
                {"name": "yi", "value": 100_000_000},
            ],
        },
        "fiscal_year": {
            "start_month": 1,
            "end_month": 12,
            "description": "Calendar year, 1 January to 31 December.",
        },
        "accounting": {
            "primary_framework": "CAS",
            "framework_id": "CAS",
            "description": (
                "Chinese Accounting Standards for Business Enterprises (CAS, also called "
                "ASBE), issued by the Ministry of Finance and substantially converged with IFRS."
            ),
            "alternatives": [],
        },
        "regulators": [
            {"short_name": "CSRC", "name": "China Securities Regulatory Commission", "role": "Securities markets"},
            {"short_name": "PBOC", "name": "People's Bank of China", "role": "Central bank"},
            {"short_name": "NFRA", "name": "National Financial Regulatory Administration", "role": "Banking and insurance supervision"},
        ],
        "exchanges": [
            {"short_name": "SSE", "name": "Shanghai Stock Exchange", "yahoo_suffix": ".SS"},
            {"short_name": "SZSE", "name": "Shenzhen Stock Exchange", "yahoo_suffix": ".SZ"},
        ],
        "indices": [
            {"name": "SSE Composite", "symbol": "000001.SS"},
            {"name": "CSI 300", "symbol": "000300.SS"},
        ],
        "fx_symbol": "CNY=X",
        "market": {
            "timezone": "Asia/Shanghai",
            "timezone_label": "CST (UTC+8)",
            "sessions": [["09:30", "11:30"], ["13:00", "15:00"]],
            "lunch_break": True,
        },
    },
    "JP": {
        "code": "JP",
        "name": "Japan",
        "currency": {"code": "JPY", "name": "Japanese yen", "symbol": "\u00a5", "minor_units": 0},
        "locale": "en-US",
        "number_grouping": {
            "style": "western",
            "description": (
                "Thousands grouping in English-language reports. Local usage counts in "
                "units of ten thousand (man) and one hundred million (oku); statements are "
                "often presented in millions of yen."
            ),
            "units": [
                {"name": "man", "value": 10_000},
                {"name": "oku", "value": 100_000_000},
            ],
        },
        "fiscal_year": {
            "start_month": 4,
            "end_month": 3,
            "description": (
                "Companies choose their own year end; 1 April to 31 March is the most "
                "common and matches the government fiscal year."
            ),
        },
        "accounting": {
            "primary_framework": "J-GAAP",
            "framework_id": "JGAAP",
            "description": (
                "Japanese GAAP is the default. Listed companies may instead use IFRS or "
                "US GAAP for consolidated statements when eligibility conditions are met."
            ),
            "alternatives": ["IFRS", "US GAAP"],
        },
        "regulators": [
            {"short_name": "FSA", "name": "Financial Services Agency", "role": "Financial sector regulation and supervision"},
            {"short_name": "BOJ", "name": "Bank of Japan", "role": "Central bank"},
            {"short_name": "SESC", "name": "Securities and Exchange Surveillance Commission", "role": "Market surveillance"},
        ],
        "exchanges": [
            {"short_name": "TSE", "name": "Tokyo Stock Exchange (Japan Exchange Group)", "yahoo_suffix": ".T"},
        ],
        "indices": [
            # TOPIX is not listed: the market data source does not serve that index.
            {"name": "Nikkei 225", "symbol": "^N225"},
        ],
        "fx_symbol": "JPY=X",
        "market": {
            "timezone": "Asia/Tokyo",
            "timezone_label": "JST (UTC+9)",
            "sessions": [["09:00", "11:30"], ["12:30", "15:30"]],
            "lunch_break": True,
        },
    },
    "KR": {
        "code": "KR",
        "name": "South Korea",
        "currency": {"code": "KRW", "name": "South Korean won", "symbol": "\u20a9", "minor_units": 0},
        "locale": "en-US",
        "number_grouping": {
            "style": "western",
            "description": (
                "Thousands grouping in English-language reports. Local usage counts in "
                "units of ten thousand (man), one hundred million (eok) and one trillion (jo)."
            ),
            "units": [
                {"name": "man", "value": 10_000},
                {"name": "eok", "value": 100_000_000},
                {"name": "jo", "value": 1_000_000_000_000},
            ],
        },
        "fiscal_year": {
            "start_month": 1,
            "end_month": 12,
            "description": "Companies choose their own year end; most use the calendar year.",
        },
        "accounting": {
            "primary_framework": "K-IFRS",
            "framework_id": "KIFRS",
            "description": (
                "Korean IFRS (K-IFRS) is mandatory for listed companies and financial "
                "institutions. Unlisted companies may use K-GAAP."
            ),
            "alternatives": ["K-GAAP (unlisted companies)"],
        },
        "regulators": [
            {"short_name": "FSC", "name": "Financial Services Commission", "role": "Financial policy and regulation"},
            {"short_name": "FSS", "name": "Financial Supervisory Service", "role": "Supervision and examination"},
            {"short_name": "BOK", "name": "Bank of Korea", "role": "Central bank"},
        ],
        "exchanges": [
            {"short_name": "KRX KOSPI", "name": "Korea Exchange, KOSPI market", "yahoo_suffix": ".KS"},
            {"short_name": "KRX KOSDAQ", "name": "Korea Exchange, KOSDAQ market", "yahoo_suffix": ".KQ"},
        ],
        "indices": [
            {"name": "KOSPI", "symbol": "^KS11"},
            {"name": "KOSDAQ", "symbol": "^KQ11"},
        ],
        "fx_symbol": "KRW=X",
        "market": {
            "timezone": "Asia/Seoul",
            "timezone_label": "KST (UTC+9)",
            "sessions": [["09:00", "15:30"]],
            "lunch_break": False,
        },
    },
}

# Optional related market shown next to the China board. It trades in Hong Kong
# dollars and keeps its own hours, so it is kept out of the four country records.
RELATED_INDICES: list[dict] = [
    {
        "name": "Hang Seng",
        "symbol": "^HSI",
        "country": "CN",
        "market_name": "Hong Kong",
        "currency": "HKD",
        "market": {
            "timezone": "Asia/Hong_Kong",
            "timezone_label": "HKT (UTC+8)",
            "sessions": [["09:30", "12:00"], ["13:00", "16:00"]],
            "lunch_break": True,
        },
    },
]


def list_countries() -> list[dict]:
    """All four country records, in display order."""
    return [COUNTRIES[code] for code in ("IN", "CN", "JP", "KR")]


def get_country(code: str) -> dict:
    """One country record by ISO 3166 alpha-2 code (case-insensitive)."""
    key = str(code).strip().upper()
    if key not in COUNTRIES:
        raise ValueError(f"Unknown country '{code}'. Available: {', '.join(COUNTRIES)}")
    return COUNTRIES[key]


def all_indices() -> list[dict]:
    """Benchmark indices for the board: [{country, name, symbol, optional}]."""
    rows = []
    for country in list_countries():
        for index in country["indices"]:
            rows.append({"country": country["code"], "name": index["name"],
                         "symbol": index["symbol"], "optional": False})
        for related in RELATED_INDICES:
            if related["country"] == country["code"]:
                rows.append({"country": country["code"], "name": related["name"],
                             "symbol": related["symbol"], "optional": True,
                             "market_name": related["market_name"]})
    return rows


def fx_pairs() -> list[dict]:
    """USD pairs for the four local currencies, quoted as local units per 1 USD."""
    return [
        {"country": c["code"], "pair": f"USD/{c['currency']['code']}",
         "currency": c["currency"]["code"], "symbol": c["fx_symbol"]}
        for c in list_countries()
    ]


def _parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def _session_status(market: dict, now: datetime | None) -> dict:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    local = current.astimezone(ZoneInfo(market["timezone"]))
    sessions = [(_parse_hhmm(start), _parse_hhmm(end)) for start, end in market["sessions"]]
    clock = local.time().replace(tzinfo=None)

    if local.weekday() >= 5:
        state = "closed"
        reason = "Weekend"
    elif any(start <= clock < end for start, end in sessions):
        state = "open"
        reason = "Regular session"
    elif sessions[0][1] <= clock < sessions[-1][0]:
        state = "break"
        reason = "Midday break"
    elif clock < sessions[0][0]:
        state = "closed"
        reason = "Before the open"
    else:
        state = "closed"
        reason = "After the close"

    return {
        "status": state,
        "is_open": state == "open",
        "reason": reason,
        "local_time": local.strftime("%Y-%m-%d %H:%M"),
        "weekday": local.strftime("%A"),
        "timezone": market["timezone"],
        "timezone_label": market["timezone_label"],
        "sessions": market["sessions"],
    }


def market_status(code: str, now: datetime | None = None) -> dict:
    """Open / break / closed for one country's main equity market.

    Simplified: regular weekday hours only, no holiday calendar.
    """
    country = get_country(code)
    return {
        "country": country["code"],
        "name": country["name"],
        **_session_status(country["market"], now),
        "note": MARKET_STATUS_NOTE,
    }


def all_market_status(now: datetime | None = None) -> list[dict]:
    """Status for the four main markets plus any related market (Hong Kong)."""
    rows = [market_status(c["code"], now) for c in list_countries()]
    for related in RELATED_INDICES:
        rows.append({
            "country": related["country"],
            "name": related["market_name"],
            "related_index": related["symbol"],
            **_session_status(related["market"], now),
            "note": MARKET_STATUS_NOTE,
        })
    return rows
