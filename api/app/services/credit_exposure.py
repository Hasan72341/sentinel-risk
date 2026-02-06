"""Daily counterparty exposure monitoring.

Each position row is expressed in its own currency. Portfolio totals are
converted to a reporting currency with caller-supplied conversion rates.

Simplified, for analysis and learning; this is a monitoring tool, not a
regulatory exposure calculation or an initial margin model.
"""

from math import isfinite

AMOUNT_KEYS = (
    "current_mtm", "previous_mtm", "collateral",
    "previous_collateral", "credit_limit", "required_margin",
)

# Severity thresholds used by the breach investigation list.
CRITICAL_LIMIT_EXCESS_PCT = 10.0   # limit excess as % of the limit
HIGH_MARGIN_DEFICIT_PCT = 25.0     # margin deficit as % of the requirement
WATCH_UTILISATION_PCT = 85.0       # utilisation that puts a name on watch
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "watch": 3}

# Illustrative static conversion rates (USD per one unit of local currency).
# They exist only so the sample book can be aggregated; they are not market data.
SAMPLE_FX_RATES_TO_USD = {"USD": 1.0, "INR": 0.012, "CNY": 0.14, "JPY": 0.0067, "KRW": 0.00073}

# Fictional clients. Amounts are in millions of the row currency.
SAMPLE_BOOK = [
    {"counterparty": "Saffron Ridge Opportunities Fund", "country": "India", "client_type": "Hedge fund", "currency": "INR",
     "current_mtm": 4850, "previous_mtm": 4120, "collateral": 900, "previous_collateral": 900,
     "credit_limit": 3500, "required_margin": 1150, "previous_required_margin": 880},
    {"counterparty": "Indus Meridian Steelworks", "country": "India", "client_type": "Corporate", "currency": "INR",
     "current_mtm": 2100, "previous_mtm": 2240, "collateral": 400, "previous_collateral": 400,
     "credit_limit": 2500, "required_margin": 380, "previous_required_margin": 380},
    {"counterparty": "Jade Heron Securities", "country": "China", "client_type": "Financial institution", "currency": "CNY",
     "current_mtm": 610, "previous_mtm": 655, "collateral": 240, "previous_collateral": 150,
     "credit_limit": 450, "required_margin": 230, "previous_required_margin": 230},
    {"counterparty": "Yellow Crane Mutual Fund", "country": "China", "client_type": "Mutual fund", "currency": "CNY",
     "current_mtm": 395, "previous_mtm": 310, "collateral": 60, "previous_collateral": 60,
     "credit_limit": 380, "required_margin": 55, "previous_required_margin": 55},
    {"counterparty": "Shirakaba Employees Pension Fund", "country": "Japan", "client_type": "Pension fund", "currency": "JPY",
     "current_mtm": 18200, "previous_mtm": 18200, "collateral": 5200, "previous_collateral": 5200,
     "credit_limit": 20000, "required_margin": 4800, "previous_required_margin": 4800},
    {"counterparty": "Hoshikawa Maritime Trading", "country": "Japan", "client_type": "Corporate", "currency": "JPY",
     "current_mtm": 9400, "previous_mtm": 7100, "collateral": 1500, "previous_collateral": 1900,
     "credit_limit": 9000, "required_margin": 2100, "previous_required_margin": 1800},
    {"counterparty": "Baekdu Ridge Hedge Fund", "country": "South Korea", "client_type": "Hedge fund", "currency": "KRW",
     "current_mtm": 152000, "previous_mtm": 171000, "collateral": 41000, "previous_collateral": 30000,
     "credit_limit": 130000, "required_margin": 40000, "previous_required_margin": 42000},
    {"counterparty": "Namsan Lantern Savings Bank", "country": "South Korea", "client_type": "Financial institution", "currency": "KRW",
     "current_mtm": -12000, "previous_mtm": 8000, "collateral": 5000, "previous_collateral": 5000,
     "credit_limit": 60000, "required_margin": 4000, "previous_required_margin": 4000},
    {"counterparty": "Pacific Lotus Global Macro Fund", "country": "Japan", "client_type": "Hedge fund", "currency": "USD",
     "current_mtm": 46, "previous_mtm": 44, "collateral": 12, "previous_collateral": 12,
     "credit_limit": 30, "required_margin": 11, "previous_required_margin": 11},
]


def sample_book() -> dict:
    """Bundled illustrative book of fictional clients (not real companies or market data)."""
    return {
        "positions": [dict(position) for position in SAMPLE_BOOK],
        "fx_rates": dict(SAMPLE_FX_RATES_TO_USD),
        "reporting_currency": "USD",
        "unit": "millions of the row currency",
        "disclaimer": (
            "Illustrative sample data. Client names are fictional and all amounts and "
            "conversion rates are invented for demonstration; none of it is market data."
        ),
    }


def _fmt(amount: float, currency: str | None) -> str:
    return f"{amount:,.2f} {currency}" if currency else f"{amount:,.2f}"


def _moved(label: str, change: float, level: float, currency: str | None) -> str:
    if change > 0:
        return f"{label} up {_fmt(change, None)}"
    if change < 0:
        return f"{label} down {_fmt(-change, None)}"
    return f"{label} unchanged at {_fmt(level, currency)}"


def _commentary(row: dict) -> str:
    ccy = row["currency"]
    change = row["day_change"]
    movement = "rose" if change > 0 else "fell" if change < 0 else "was unchanged"
    text = f"Net exposure {movement}"
    if change:
        text += f" by {abs(change):,.2f} to {_fmt(row['net_exposure'], ccy)}"
    else:
        text += f" at {_fmt(row['net_exposure'], ccy)}"
    text += (
        f": {_moved('MTM', row['mtm_change'], row['current_mtm'], ccy)}, "
        f"{_moved('collateral', row['collateral_change'], row['collateral'], ccy)}."
    )

    status = row["limit_breach_status"]
    if status == "opened":
        text += (f" Credit limit breach opened: {_fmt(row['limit_breach'], ccy)} over the "
                 f"{_fmt(row['credit_limit'], ccy)} limit ({row['limit_utilization_pct']:.1f}% utilised).")
    elif status == "ongoing":
        text += (f" Credit limit breach persists: {_fmt(row['limit_breach'], ccy)} over the "
                 f"{_fmt(row['credit_limit'], ccy)} limit ({row['limit_utilization_pct']:.1f}% utilised).")
    elif status == "closed":
        text += f" Credit limit breach closed; utilisation back to {row['limit_utilization_pct']:.1f}%."

    margin = row["margin_status"]
    if margin == "call_triggered":
        text += (f" Margin call triggered for {_fmt(row['margin_shortfall'], ccy)}: collateral "
                 f"{_fmt(row['collateral'], ccy)} against a requirement of {_fmt(row['margin_requirement'], ccy)}.")
    elif margin == "deficit_outstanding":
        text += (f" Margin deficit outstanding: collateral is {_fmt(row['margin_shortfall'], ccy)} "
                 f"below the {_fmt(row['margin_requirement'], ccy)} requirement.")
    elif margin == "cured":
        text += f" Margin deficit cured; excess now {_fmt(row['margin_excess'], ccy)}."
    return text


def _review_row(position: dict) -> dict:
    name = str(position["counterparty"]).strip()
    if not name:
        raise ValueError("counterparty is required")
    values = {key: float(position[key]) for key in AMOUNT_KEYS}
    previous_required = position.get("previous_required_margin")
    values["previous_required_margin"] = (
        values["required_margin"] if previous_required is None else float(previous_required)
    )
    if not all(isfinite(value) for value in values.values()):
        raise ValueError(f"{name}: all amounts must be finite")
    if values["credit_limit"] <= 0:
        raise ValueError(f"{name}: credit_limit must be greater than zero")
    for key in ("collateral", "previous_collateral", "required_margin", "previous_required_margin"):
        if values[key] < 0:
            raise ValueError(f"{name}: {key} cannot be negative")

    currency = (str(position.get("currency") or "").strip().upper()) or None
    limit = values["credit_limit"]
    current = max(values["current_mtm"] - values["collateral"], 0)
    previous = max(values["previous_mtm"] - values["previous_collateral"], 0)
    breach = max(current - limit, 0)
    previous_breach = max(previous - limit, 0)
    margin_excess = values["collateral"] - values["required_margin"]
    shortfall = max(-margin_excess, 0)
    previous_shortfall = max(values["previous_required_margin"] - values["previous_collateral"], 0)

    if breach > 0:
        limit_status = "ongoing" if previous_breach > 0 else "opened"
    else:
        limit_status = "closed" if previous_breach > 0 else "none"
    if shortfall > 0:
        margin_status = "deficit_outstanding" if previous_shortfall > 0 else "call_triggered"
    else:
        margin_status = "cured" if previous_shortfall > 0 else "none"

    row = {
        "counterparty": name,
        "country": (str(position.get("country") or "").strip()) or None,
        "client_type": (str(position.get("client_type") or "").strip()) or None,
        "currency": currency,
        "current_mtm": round(values["current_mtm"], 2),
        "exposure": round(max(values["current_mtm"], 0), 2),
        "collateral": round(values["collateral"], 2),
        "net_exposure": round(current, 2),
        "previous_net_exposure": round(previous, 2),
        "day_change": round(current - previous, 2),
        "mtm_change": round(values["current_mtm"] - values["previous_mtm"], 2),
        "collateral_change": round(values["collateral"] - values["previous_collateral"], 2),
        "credit_limit": round(limit, 2),
        "limit_utilization_pct": round(current / limit * 100, 2),
        "limit_breach": round(breach, 2),
        "limit_breach_flag": breach > 0,
        "limit_breach_status": limit_status,
        "margin_requirement": round(values["required_margin"], 2),
        "margin_excess": round(margin_excess, 2),
        "margin_shortfall": round(shortfall, 2),
        "margin_call_flag": shortfall > 0,
        "margin_status": margin_status,
    }
    row["commentary"] = _commentary(row)
    return row


def review_exposures(positions: list[dict]) -> list[dict]:
    """Review each counterparty row in its own currency.

    Net exposure is max(MTM - collateral, 0). Margin excess is collateral
    minus the margin requirement (negative means a deficit). Limit and margin
    statuses compare today with the previous day.
    """
    results = [_review_row(position) for position in positions]
    return sorted(
        results,
        key=lambda row: (row["limit_breach"] > 0, row["margin_shortfall"] > 0, row["net_exposure"]),
        reverse=True,
    )


def _conversion_rates(rows: list[dict], reporting_currency: str | None, fx_rates: dict | None) -> tuple[str | None, dict]:
    """Rate that converts each row currency into the reporting currency."""
    currencies = {row["currency"] for row in rows}
    reporting = (reporting_currency or "").strip().upper() or None
    if reporting is None:
        if len(currencies) > 1:
            raise ValueError("reporting_currency is required when positions use more than one currency")
        reporting = next(iter(currencies))
    rates = {str(code).strip().upper(): float(rate) for code, rate in (fx_rates or {}).items()}
    for code, rate in rates.items():
        # Every supplied rate is checked: the reporting currency's own rate is the divisor.
        if not isfinite(rate) or rate <= 0:
            raise ValueError(f"fx_rates[{code}] must be a positive number")
    resolved = {}
    for currency in currencies:
        if currency is None or currency == reporting:
            resolved[currency] = 1.0
            continue
        rate = rates.get(currency)
        if rate is None:
            raise ValueError(f"fx_rates is missing a rate for {currency} into {reporting}")
        # Rates may be quoted against a third currency (for example all in USD).
        resolved[currency] = rate / rates.get(reporting, 1.0)
    return reporting, resolved


def _breach_items(row: dict, rate: float, reporting: str | None) -> list[dict]:
    items = []
    base = {"counterparty": row["counterparty"], "country": row["country"], "currency": row["currency"],
            "reporting_currency": reporting}
    if row["limit_breach"] > 0:
        excess_pct = row["limit_breach"] / row["credit_limit"] * 100
        items.append({
            **base, "type": "limit_breach",
            "severity": "critical" if excess_pct >= CRITICAL_LIMIT_EXCESS_PCT else "high",
            "status": "new" if row["limit_breach_status"] == "opened" else "ongoing",
            "amount": row["limit_breach"], "amount_reporting": round(row["limit_breach"] * rate, 2),
            "pct": round(excess_pct, 2),
            "detail": (f"Net exposure {_fmt(row['net_exposure'], row['currency'])} exceeds the "
                       f"{_fmt(row['credit_limit'], row['currency'])} limit by {excess_pct:.1f}%."),
            "action": ("Escalate to the credit officer; confirm the MTM driver, then reduce exposure, "
                       "call additional collateral or seek a temporary limit increase."),
        })
    elif row["limit_utilization_pct"] >= WATCH_UTILISATION_PCT:
        headroom = row["credit_limit"] - row["net_exposure"]
        items.append({
            **base, "type": "limit_watch", "severity": "watch", "status": "watch",
            "amount": round(headroom, 2), "amount_reporting": round(headroom * rate, 2),
            "pct": row["limit_utilization_pct"],
            "detail": (f"Utilisation {row['limit_utilization_pct']:.1f}% with "
                       f"{_fmt(headroom, row['currency'])} headroom left."),
            "action": "Monitor intraday; pre-clear any new trades against the remaining headroom.",
        })
    if row["margin_shortfall"] > 0:
        requirement = row["margin_requirement"]
        deficit_pct = row["margin_shortfall"] / requirement * 100
        items.append({
            **base, "type": "margin_deficit",
            "severity": "high" if deficit_pct >= HIGH_MARGIN_DEFICIT_PCT else "medium",
            "status": "new" if row["margin_status"] == "call_triggered" else "ongoing",
            "amount": row["margin_shortfall"], "amount_reporting": round(row["margin_shortfall"] * rate, 2),
            "pct": round(deficit_pct, 2),
            "detail": (f"Collateral {_fmt(row['collateral'], row['currency'])} is {deficit_pct:.1f}% short of the "
                       f"{_fmt(requirement, row['currency'])} margin requirement."),
            "action": "Issue or chase the margin call and confirm the settlement date with the client.",
        })
    return items


def review_book(positions: list[dict], reporting_currency: str | None = None, fx_rates: dict | None = None) -> dict:
    """Row-level review plus a portfolio summary and a breach investigation list.

    fx_rates maps a currency code to the value of one unit of that currency.
    All rates must share one quote currency (for example all quoted in USD);
    the reporting currency then needs either to be that quote currency or to
    appear in the mapping. Rows without a currency are treated as already
    being in the reporting currency.
    """
    rows = review_exposures(positions)
    reporting, rates = _conversion_rates(rows, reporting_currency, fx_rates)

    def total(key: str) -> float:
        return round(sum(row[key] * rates[row["currency"]] for row in rows), 2)

    breaches = []
    by_country: dict[str, dict] = {}
    for row in rows:
        rate = rates[row["currency"]]
        row["net_exposure_reporting"] = round(row["net_exposure"] * rate, 2)
        row["day_change_reporting"] = round(row["day_change"] * rate, 2)
        breaches.extend(_breach_items(row, rate, reporting))
        bucket = by_country.setdefault(row["country"] or "Unspecified", {
            "country": row["country"] or "Unspecified", "clients": 0, "net_exposure": 0.0, "day_change": 0.0,
        })
        bucket["clients"] += 1
        bucket["net_exposure"] = round(bucket["net_exposure"] + row["net_exposure_reporting"], 2)
        bucket["day_change"] = round(bucket["day_change"] + row["day_change_reporting"], 2)
    # Most severe first; within a level the largest amount (or, for watch items, the highest utilisation).
    breaches.sort(key=lambda item: (
        SEVERITY_ORDER[item["severity"]],
        -item["pct"] if item["severity"] == "watch" else -item["amount_reporting"],
    ))

    net = total("net_exposure")
    previous_net = total("previous_net_exposure")
    change = round(net - previous_net, 2)
    limit_breaches = [row for row in rows if row["limit_breach_flag"]]
    margin_calls = [row for row in rows if row["margin_call_flag"]]
    mover = max(rows, key=lambda row: abs(row["day_change_reporting"]))

    direction = "rose" if change > 0 else "fell" if change < 0 else "was unchanged"
    headline = f"Book net exposure {direction}"
    if change:
        pct = f" ({abs(change) / previous_net * 100:.1f}%)" if previous_net > 0 else ""
        headline += f" by {_fmt(abs(change), None)}{pct} to {_fmt(net, reporting)}"
    else:
        headline += f" at {_fmt(net, reporting)}"
    headline += f" across {len(rows)} client{'s' if len(rows) != 1 else ''}."
    if mover["day_change_reporting"]:
        move = f"{mover['day_change_reporting']:+,.2f} {reporting or ''}".rstrip()
        headline += f" Largest move: {mover['counterparty']} ({move})."
    opened = sum(row["limit_breach_status"] == "opened" for row in rows)
    closed = sum(row["limit_breach_status"] == "closed" for row in rows)
    headline += (f" {len(limit_breaches)} limit breach{'es' if len(limit_breaches) != 1 else ''} open"
                 f" ({opened} new, {closed} closed today)")
    headline += f" and {len(margin_calls)} margin deficit{'s' if len(margin_calls) != 1 else ''}"
    headline += f" totalling {_fmt(total('margin_shortfall'), reporting)}." if margin_calls else "."

    summary = {
        "reporting_currency": reporting,
        "clients": len(rows),
        "gross_exposure": total("exposure"),
        "collateral": total("collateral"),
        "net_exposure": net,
        "previous_net_exposure": previous_net,
        "day_change": change,
        "margin_requirement": total("margin_requirement"),
        "margin_deficit": total("margin_shortfall"),
        "limit_breach_amount": total("limit_breach"),
        "limit_breach_count": len(limit_breaches),
        "limit_breaches_opened": opened,
        "limit_breaches_closed": closed,
        "margin_call_count": len(margin_calls),
        "margin_calls_triggered": sum(row["margin_status"] == "call_triggered" for row in rows),
        "largest_mover": mover["counterparty"] if mover["day_change_reporting"] else None,
        "by_country": sorted(by_country.values(), key=lambda bucket: -bucket["net_exposure"]),
        "commentary": headline,
    }
    return {"results": rows, "summary": summary, "breaches": breaches}
