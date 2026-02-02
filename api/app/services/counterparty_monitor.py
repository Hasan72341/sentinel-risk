"""Counterparty portfolio monitoring: reviews due, migrations, watchlist, actions.

Simplified, for analysis and learning; not a regulatory calculation. Limits
and utilisation must be in one currency (USD millions in the sample data).

Rules
-----
* Next review date = last review date + 12 months (annual) or + 6 months
  (semi-annual). A review is ``overdue`` when the next review date is before
  the as-of date and ``due_soon`` when it falls within 30 days.
* Rating migration = number of notches between the previous and current
  internal grade (IR1 strongest, IR10 weakest). Positive notches = downgrade.
* Utilisation % = utilisation / limit. Above 100% is a limit breach; 90% or
  more is high utilisation.
* Watchlist flags: weak grade (IR7 or weaker), downgrade of two or more
  notches, limit breach, high utilisation, review overdue.
* Each condition adds points to a priority score and an action to the action
  list: limit breach 100, review overdue 60, downgrade of two or more notches
  50, weak grade 40, high utilisation 30, review due soon 20, one-notch
  downgrade 15. Priority is High at 100 points or more, Medium at 40 or more,
  otherwise Low.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from math import isfinite

from app.services.credit_rating import COUNTERPARTY_TYPES, COUNTRIES, GRADES, TYPE_LABELS

REVIEW_MONTHS = {"annual": 12, "semi_annual": 6}
DUE_SOON_DAYS = 30
HIGH_UTILISATION_PCT = 90.0
WEAK_GRADE_INDEX = GRADES.index("IR7")

PRIORITY_POINTS = {
    "limit_breach": 100, "review_overdue": 60, "multi_notch_downgrade": 50,
    "weak_grade": 40, "high_utilisation": 30, "review_due_soon": 20, "downgrade": 15,
}


def add_months(start: date, months: int) -> date:
    """Add calendar months, clamping to the last day of the target month."""
    year, month = divmod(start.month - 1 + months, 12)
    year += start.year
    month += 1
    return date(year, month, min(start.day, monthrange(year, month)[1]))


def _to_date(value, field: str, name: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{name}: {field} must be an ISO date (YYYY-MM-DD)") from exc


def _priority(score: int) -> str:
    return "High" if score >= 100 else "Medium" if score >= 40 else "Low"


def review_portfolio(counterparties: list[dict], as_of: date | str | None = None) -> dict:
    """Review a counterparty portfolio as of a date (default: today).

    Returns one row per counterparty plus reviews due, rating migrations,
    watchlist, a prioritised action list and a summary. See the module
    docstring for the rules.
    """
    as_of = date.today() if as_of is None else _to_date(as_of, "as_of", "request")
    if not counterparties:
        raise ValueError("at least one counterparty is required")

    rows = []
    seen = set()
    for item in counterparties:
        name = str(item.get("name", "")).strip()
        if not name:
            raise ValueError("counterparty name is required")
        if name in seen:
            raise ValueError(f"{name}: duplicate counterparty name")
        seen.add(name)
        kind = item.get("counterparty_type")
        if kind not in COUNTERPARTY_TYPES:
            raise ValueError(f"{name}: counterparty_type must be one of: {', '.join(COUNTERPARTY_TYPES)}")
        country = item.get("country")
        if country not in COUNTRIES:
            raise ValueError(f"{name}: country must be one of: {', '.join(COUNTRIES)}")
        rating = item.get("rating")
        previous = item.get("previous_rating") or rating
        if rating not in GRADES or previous not in GRADES:
            raise ValueError(f"{name}: ratings must be internal grades IR1 to IR10")
        frequency = item.get("review_frequency")
        if frequency not in REVIEW_MONTHS:
            raise ValueError(f"{name}: review_frequency must be 'annual' or 'semi_annual'")
        last_review = _to_date(item.get("last_review_date"), "last_review_date", name)
        if last_review > as_of:
            raise ValueError(f"{name}: last_review_date cannot be after the as-of date")
        limit, utilisation = float(item.get("limit", 0)), float(item.get("utilisation", 0))
        if not (isfinite(limit) and isfinite(utilisation)):
            raise ValueError(f"{name}: limit and utilisation must be finite")
        if limit <= 0:
            raise ValueError(f"{name}: limit must be greater than zero")
        if utilisation < 0:
            raise ValueError(f"{name}: utilisation cannot be negative")

        next_review = add_months(last_review, REVIEW_MONTHS[frequency])
        days_to_review = (next_review - as_of).days
        review_status = "overdue" if days_to_review < 0 else "due_soon" if days_to_review <= DUE_SOON_DAYS else "current"
        notches = GRADES.index(rating) - GRADES.index(previous)
        direction = "downgrade" if notches > 0 else "upgrade" if notches < 0 else "stable"
        utilisation_pct = utilisation / limit * 100
        breach = max(utilisation - limit, 0.0)

        flags, actions, score = [], [], 0

        def add(code: str, flag: str | None, action: str) -> None:
            nonlocal score
            score += PRIORITY_POINTS[code]
            if flag:
                flags.append(flag)
            actions.append(action)

        if breach > 0:
            add("limit_breach", "Limit breach",
                f"Investigate limit breach of {breach:,.1f} ({utilisation_pct:.0f}% of limit) and agree remediation.")
        elif utilisation_pct >= HIGH_UTILISATION_PCT:
            add("high_utilisation", "High utilisation",
                f"Utilisation at {utilisation_pct:.0f}% of limit: confirm pipeline and consider a limit review.")
        if review_status == "overdue":
            add("review_overdue", "Review overdue",
                f"Complete credit review, overdue by {-days_to_review} days (was due {next_review.isoformat()}).")
        elif review_status == "due_soon":
            add("review_due_soon", None,
                f"Schedule credit review, due in {days_to_review} days ({next_review.isoformat()}).")
        if notches >= 2:
            add("multi_notch_downgrade", f"Downgraded {notches} notches",
                f"Reassess limit and collateral terms after downgrade from {previous} to {rating}.")
        elif notches == 1:
            add("downgrade", None, f"Note one-notch downgrade from {previous} to {rating} in the next review.")
        if GRADES.index(rating) >= WEAK_GRADE_INDEX:
            add("weak_grade", f"Weak grade {rating}",
                f"Grade {rating}: keep on watchlist with semi-annual or more frequent review.")

        rows.append({
            "name": name,
            "counterparty_type": kind,
            "counterparty_type_label": TYPE_LABELS[kind],
            "country": country,
            "country_name": COUNTRIES[country]["name"],
            "rating": rating,
            "previous_rating": previous,
            "migration_notches": notches,
            "migration": direction,
            "review_frequency": frequency,
            "last_review_date": last_review.isoformat(),
            "next_review_date": next_review.isoformat(),
            "days_to_review": days_to_review,
            "review_status": review_status,
            "limit": round(limit, 2),
            "utilisation": round(utilisation, 2),
            "utilisation_pct": round(utilisation_pct, 1),
            "headroom": round(limit - utilisation, 2),
            "limit_breach": round(breach, 2),
            "watchlist": bool(flags),
            "watchlist_flags": flags,
            "priority_score": score,
            "priority": _priority(score) if score else "None",
            "actions": actions,
        })

    reviews_due = sorted((r for r in rows if r["review_status"] != "current"), key=lambda r: r["days_to_review"])
    migrations = sorted((r for r in rows if r["migration_notches"]), key=lambda r: r["migration_notches"], reverse=True)
    action_list = [
        {"name": r["name"], "priority": r["priority"], "priority_score": r["priority_score"], "action": action}
        for r in sorted(rows, key=lambda r: r["priority_score"], reverse=True) for action in r["actions"]
    ]

    def breakdown(key: str, label_key: str) -> list[dict]:
        groups: dict[str, dict] = {}
        for r in rows:
            group = groups.setdefault(r[key], {"key": r[key], "label": r[label_key], "count": 0, "limit": 0.0, "utilisation": 0.0})
            group["count"] += 1
            group["limit"] = round(group["limit"] + r["limit"], 2)
            group["utilisation"] = round(group["utilisation"] + r["utilisation"], 2)
        return list(groups.values())

    total_limit = sum(r["limit"] for r in rows)
    total_utilisation = sum(r["utilisation"] for r in rows)
    return {
        "as_of": as_of.isoformat(),
        "summary": {
            "counterparties": len(rows),
            "total_limit": round(total_limit, 2),
            "total_utilisation": round(total_utilisation, 2),
            "utilisation_pct": round(total_utilisation / total_limit * 100, 1),
            "reviews_overdue": sum(1 for r in rows if r["review_status"] == "overdue"),
            "reviews_due_soon": sum(1 for r in rows if r["review_status"] == "due_soon"),
            "upgrades": sum(1 for r in rows if r["migration"] == "upgrade"),
            "downgrades": sum(1 for r in rows if r["migration"] == "downgrade"),
            "limit_breaches": sum(1 for r in rows if r["limit_breach"] > 0),
            "watchlist": sum(1 for r in rows if r["watchlist"]),
            "by_country": breakdown("country", "country_name"),
            "by_type": breakdown("counterparty_type", "counterparty_type_label"),
        },
        "counterparties": sorted(rows, key=lambda r: (-r["priority_score"], r["name"])),
        "reviews_due": reviews_due,
        "migrations": migrations,
        "watchlist": [r for r in sorted(rows, key=lambda r: r["priority_score"], reverse=True) if r["watchlist"]],
        "actions": action_list,
        "disclaimer": "Simplified monitoring rules for analysis and learning; not a regulatory calculation.",
    }


# name, type, country, rating, previous rating, frequency, days since last review, limit, utilisation
_SAMPLE_ROWS = (
    ("Saffron Ridge Industries (sample)", "corporate", "IN", "IR4", "IR4", "annual", 120, 150.0, 82.0),
    ("Lotus Grid Utilities (sample)", "corporate", "IN", "IR5", "IR4", "annual", 350, 90.0, 61.0),
    ("Jade Harbour Components (sample)", "corporate", "CN", "IR6", "IR5", "semi_annual", 200, 110.0, 104.5),
    ("Kitsune Precision Works (sample)", "corporate", "JP", "IR2", "IR3", "annual", 60, 600.0, 210.0),
    ("Baram Marine Engineering (sample)", "corporate", "KR", "IR8", "IR6", "semi_annual", 150, 15.0, 17.2),
    ("Monsoon Coast Bank (sample)", "financial_institution", "IN", "IR5", "IR5", "annual", 300, 320.0, 150.0),
    ("Pearl Delta Commercial Bank (sample)", "financial_institution", "CN", "IR3", "IR3", "annual", 400, 1400.0, 980.0),
    ("Hinoki Bridge Trust Bank (sample)", "financial_institution", "JP", "IR3", "IR3", "annual", 30, 1400.0, 520.0),
    ("Dolsan Harbour Securities (sample)", "financial_institution", "KR", "IR6", "IR6", "semi_annual", 170, 90.0, 83.0),
    ("Indus Valley Equity Mutual Fund (sample)", "fund", "IN", "IR4", "IR4", "annual", 210, 65.0, 20.0),
    ("Yellow River Macro Fund (sample)", "fund", "CN", "IR7", "IR6", "semi_annual", 90, 8.0, 5.5),
    ("Momiji Lifetime Pension Fund (sample)", "fund", "JP", "IR2", "IR2", "annual", 250, 740.0, 310.0),
    ("Han River Relative Value Fund (sample)", "fund", "KR", "IR9", "IR7", "semi_annual", 45, 4.0, 3.9),
)


def sample_portfolio(as_of: date | str | None = None) -> dict:
    """Bundled portfolio of fictional counterparties (USD millions).

    Illustrative sample data: names are fictional and figures are invented.
    Review dates are set relative to the as-of date so the sample always shows
    a mix of current, due and overdue reviews.
    """
    as_of = date.today() if as_of is None else _to_date(as_of, "as_of", "request")
    return {
        "as_of": as_of.isoformat(),
        "currency": "USD mn",
        "note": "Illustrative sample data. All counterparties are fictional and all figures are invented.",
        "counterparties": [
            {"name": name, "counterparty_type": kind, "country": country, "rating": rating,
             "previous_rating": previous, "review_frequency": frequency,
             "last_review_date": (as_of - timedelta(days=days)).isoformat(),
             "limit": limit, "utilisation": utilisation}
            for name, kind, country, rating, previous, frequency, days, limit, utilisation in _SAMPLE_ROWS
        ],
    }
