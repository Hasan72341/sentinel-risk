"""Financial statement presentation and consistency checks.

Runs generic checks that hold under every supported framework (IFRS, Ind AS,
CAS, J-GAAP, K-IFRS): the balance sheet balances, the primary statements are
present, comparatives are given, subtotals and signs are consistent, and a
disclosure checklist is answered.

Simplified, for analysis and learning. It works on summary figures only and is
not an audit, a legal opinion or a complete compliance review under any
framework.
"""

from math import isfinite

DISCLAIMER = (
    "Simplified presentation and consistency checks on summary figures, for analysis "
    "and learning. Not an audit and not a complete compliance review under any framework."
)

DEFAULT_TOLERANCE_PCT = 0.5

FRAMEWORKS: dict[str, dict] = {
    "IFRS": {
        "id": "IFRS",
        "name": "IFRS Accounting Standards",
        "jurisdiction": "International",
        "issuer": "International Accounting Standards Board (IASB)",
        "equity_statement": "Statement of changes in equity",
        "notes": [
            "Items of income or expense may not be presented as extraordinary items.",
            "IFRS 18 replaces IAS 1 for annual periods beginning on or after 1 January 2027.",
        ],
    },
    "IND_AS": {
        "id": "IND_AS",
        "name": "Indian Accounting Standards (Ind AS)",
        "jurisdiction": "India",
        "issuer": "Ministry of Corporate Affairs",
        "equity_statement": "Statement of changes in equity",
        "notes": [
            "Converged with IFRS, with some India-specific differences.",
            "Statement formats follow Schedule III of the Companies Act, 2013.",
            "The usual financial year runs from 1 April to 31 March.",
        ],
    },
    "CAS": {
        "id": "CAS",
        "name": "Chinese Accounting Standards for Business Enterprises (CAS)",
        "jurisdiction": "China",
        "issuer": "Ministry of Finance",
        "equity_statement": "Statement of changes in owners' equity",
        "notes": [
            "Substantially converged with IFRS.",
            "The financial year is the calendar year.",
            "Statement formats are prescribed by the Ministry of Finance.",
        ],
    },
    "JGAAP": {
        "id": "JGAAP",
        "name": "Japanese GAAP (J-GAAP)",
        "jurisdiction": "Japan",
        "issuer": "Accounting Standards Board of Japan (ASBJ)",
        "equity_statement": "Statement of changes in net assets",
        "notes": [
            "Listed companies may instead use IFRS or US GAAP for consolidated statements when eligible.",
            "Goodwill is amortised, and extraordinary gains and losses are presented separately.",
            "Ordinary income is presented as a subtotal below operating income.",
        ],
    },
    "KIFRS": {
        "id": "KIFRS",
        "name": "Korean IFRS (K-IFRS)",
        "jurisdiction": "South Korea",
        "issuer": "Korea Accounting Standards Board (KASB)",
        "equity_statement": "Statement of changes in equity",
        "notes": [
            "Mandatory for listed companies and financial institutions.",
            "Operating profit is presented on the face of the income statement.",
        ],
    },
}

STATEMENTS = [
    ("balance_sheet", "Balance sheet (statement of financial position)"),
    ("income_statement", "Income statement (statement of profit or loss)"),
    ("cash_flow_statement", "Statement of cash flows"),
    ("changes_in_equity", None),  # label comes from the framework
    ("notes", "Notes, including accounting policies"),
]

DISCLOSURE_ITEMS = [
    ("basis_of_preparation", "Basis of preparation and the framework applied are stated"),
    ("accounting_policies", "Material accounting policies are disclosed"),
    ("going_concern", "Going concern assessment and any material uncertainties are disclosed"),
    ("related_parties", "Related party relationships and transactions are disclosed"),
    ("segment_information", "Segment information is disclosed (listed entities)"),
    ("earnings_per_share", "Earnings per share is presented (listed entities)"),
    ("contingent_liabilities", "Contingent liabilities and commitments are disclosed"),
    ("subsequent_events", "Events after the reporting period are disclosed"),
    ("financial_risk", "Financial instrument risks (credit, liquidity, market) are disclosed"),
]

CATEGORIES = {
    "presentation": "Statement presentation",
    "balance_sheet": "Balance sheet consistency",
    "income_statement": "Income statement consistency",
    "cash_flow": "Cash flow consistency",
    "signs": "Sign and range checks",
    "comparatives": "Comparative information",
    "disclosure": "Disclosure checklist",
}

CHECK_CATALOGUE = [
    ("PRES_01", "presentation", "blocking", "A complete set of financial statements is present"),
    ("BS_01", "balance_sheet", "blocking", "Total assets equal total liabilities plus total equity"),
    ("BS_02", "balance_sheet", "warning", "Current and non-current assets add up to total assets"),
    ("BS_03", "balance_sheet", "warning", "Current and non-current liabilities add up to total liabilities"),
    ("IS_01", "income_statement", "warning", "Revenue less cost of sales equals gross profit"),
    ("IS_02", "income_statement", "warning", "Profit before tax less tax expense equals net income"),
    ("CF_01", "cash_flow", "warning", "Operating, investing and financing cash flows add up to the net change in cash"),
    ("CF_02", "cash_flow", "warning", "Opening cash plus the net change equals closing cash"),
    ("SIGN_01", "signs", "warning", "Amounts that cannot be negative are not negative"),
    ("SIGN_02", "signs", "warning", "Components do not exceed their totals"),
    ("SIGN_03", "signs", "warning", "Total equity is positive"),
    ("COMP_01", "comparatives", "warning", "Prior-period comparatives are presented"),
    ("COMP_02", "comparatives", "info", "Change in equity is explained by net income, dividends and other movements"),
] + [(f"DISC_{i:02d}", "disclosure", "warning", label) for i, (_, label) in enumerate(DISCLOSURE_ITEMS, 1)]


def resolve_framework(framework: str) -> dict:
    """Framework record from an id such as 'IND_AS', 'Ind AS', 'j-gaap' or 'K-IFRS'."""
    key = str(framework).strip().upper().replace("-", "").replace(" ", "").replace("_", "")
    for framework_id, record in FRAMEWORKS.items():
        if key == framework_id.replace("_", ""):
            return record
    raise ValueError(f"Unknown framework '{framework}'. Available: {', '.join(FRAMEWORKS)}")


def get_frameworks() -> list[dict]:
    return list(FRAMEWORKS.values())


def get_compliance_standards() -> list[dict]:
    """Check catalogue grouped by category (same for every framework)."""
    return [
        {"code": category, "name": name,
         "check_count": sum(1 for check in CHECK_CATALOGUE if check[1] == category)}
        for category, name in CATEGORIES.items()
    ]


def get_checks() -> list[dict]:
    return [
        {"check_id": check_id, "category": category, "standard": CATEGORIES[category],
         "severity": severity, "rule": rule}
        for check_id, category, severity, rule in CHECK_CATALOGUE
    ]


def _clean(data: dict | None) -> dict[str, float]:
    """Keep finite numeric fields only. Raises ValueError on non-finite numbers."""
    values = {}
    for key, raw in (data or {}).items():
        if raw is None or isinstance(raw, bool) or not isinstance(raw, (int, float)):
            continue
        number = float(raw)
        if not isfinite(number):
            raise ValueError(f"{key}: amount must be finite")
        values[key] = number
    return values


def _have(fd: dict, *keys: str) -> bool:
    return all(key in fd for key in keys)


def _reconcile(expected: float, actual: float, tolerance_pct: float) -> tuple[bool, float]:
    """(within tolerance, difference). Tolerance is a percentage of the larger amount."""
    difference = actual - expected
    scale = max(abs(expected), abs(actual))
    return abs(difference) <= scale * tolerance_pct / 100, difference


def _result(status: str, message: str, remediation: str | None = None) -> dict:
    result = {"status": status, "message": message}
    if remediation:
        result["remediation"] = remediation
    return result


def _sum_check(fd, parts, total, label, tolerance_pct, remediation, optional=()):
    """Check that ``parts`` (plus any supplied ``optional`` parts) add up to ``total``."""
    if not _have(fd, total, *parts):
        return _result("not_applicable", f"Not enough data to check {label}")
    expected = sum(fd[part] for part in parts) + sum(fd.get(part, 0.0) for part in optional)
    ok, difference = _reconcile(expected, fd[total], tolerance_pct)
    if ok:
        return _result("pass", f"{label} reconciles within {tolerance_pct:g}% tolerance")
    return _result(
        "fail",
        f"{label} does not reconcile: components give {expected:,.2f}, "
        f"reported {fd[total]:,.2f} (difference {difference:,.2f})",
        remediation,
    )


def _statements_check(fd: dict, statements_present, framework: dict) -> dict:
    labels = {key: label or framework["equity_statement"] for key, label in STATEMENTS}
    if statements_present is not None:
        present = {str(item).strip().lower() for item in statements_present}
        unknown = present - set(labels)
        if unknown:
            raise ValueError(f"Unknown statement(s): {', '.join(sorted(unknown))}. Use: {', '.join(labels)}")
        missing = [labels[key] for key in labels if key not in present]
        if missing:
            return _result("fail", "Missing: " + "; ".join(missing),
                           "Obtain the missing statements before relying on this set of accounts")
        return _result("pass", "All five components of a complete set are present")

    inferred = {
        "balance_sheet": _have(fd, "total_assets"),
        "income_statement": "revenue" in fd or "net_income" in fd,
        "cash_flow_statement": "operating_cash_flow" in fd,
    }
    missing = [labels[key] for key, found in inferred.items() if not found]
    if missing:
        return _result("fail", "No figures supplied for: " + "; ".join(missing),
                       "Provide the missing statements, or list the statements you hold")
    return _result(
        "not_applicable",
        f"Figures cover the three primary statements. Confirm manually that the "
        f"{framework['equity_statement'].lower()} and the notes are also present",
    )


def _signs_check(fd: dict) -> dict:
    non_negative = ("total_assets", "current_assets", "non_current_assets", "cash",
                    "inventory", "receivables", "total_liabilities", "current_liabilities",
                    "non_current_liabilities", "revenue", "cost_of_sales")
    checked = [key for key in non_negative if key in fd]
    if not checked:
        return _result("not_applicable", "No amounts supplied for sign checks")
    negative = [key for key in checked if fd[key] < 0]
    if negative:
        return _result("fail", "Negative amount(s) where a positive balance is expected: " + ", ".join(negative),
                       "Check the sign convention used when the figures were extracted")
    return _result("pass", f"{len(checked)} amount(s) checked, none negative")


def _components_check(fd: dict) -> dict:
    pairs = (("current_assets", "total_assets"), ("non_current_assets", "total_assets"),
             ("cash", "current_assets"), ("inventory", "current_assets"),
             ("receivables", "current_assets"), ("current_liabilities", "total_liabilities"),
             ("non_current_liabilities", "total_liabilities"))
    checked = [(part, total) for part, total in pairs if _have(fd, part, total)]
    if not checked:
        return _result("not_applicable", "No component and total pairs supplied")
    over = [f"{part} exceeds {total}" for part, total in checked if fd[part] > fd[total]]
    if over:
        return _result("fail", "; ".join(over), "Check line item classification and extraction")
    return _result("pass", f"{len(checked)} component(s) checked against their totals")


def _equity_sign_check(fd: dict) -> dict:
    if "total_equity" not in fd:
        return _result("not_applicable", "Total equity not supplied")
    if fd["total_equity"] <= 0:
        return _result("fail", f"Total equity is {fd['total_equity']:,.2f}",
                       "Negative or nil equity is possible but calls for a going concern assessment and disclosure")
    return _result("pass", "Total equity is positive")


def _comparatives_check(fd: dict, prior: dict) -> dict:
    if not prior:
        return _result("fail", "No prior-period figures supplied",
                       "Every supported framework requires comparative information for the preceding period")
    shared = sorted(set(fd) & set(prior))
    if not shared:
        return _result("fail", "Prior-period figures do not cover any current-period line item",
                       "Provide comparatives for the same line items as the current period")
    return _result("pass", f"Comparatives supplied for {len(shared)} line item(s)")


def _equity_rollforward_check(fd: dict, prior: dict, tolerance_pct: float) -> dict:
    if not (_have(fd, "total_equity", "net_income", "dividends") and "total_equity" in prior):
        return _result("not_applicable",
                       "Needs current and prior total equity, net income and dividends")
    expected = prior["total_equity"] + fd["net_income"] - fd["dividends"] + fd.get("other_equity_movements", 0.0)
    ok, difference = _reconcile(expected, fd["total_equity"], tolerance_pct)
    if ok:
        return _result("pass", f"Equity roll-forward reconciles within {tolerance_pct:g}% tolerance")
    return _result(
        "fail",
        f"Equity roll-forward gives {expected:,.2f}, reported {fd['total_equity']:,.2f} "
        f"(unexplained {difference:,.2f})",
        "Look for other comprehensive income, share issues or buybacks in the equity statement",
    )


def run_compliance_check(
    financial_data: dict,
    framework: str = "IFRS",
    prior_period: dict | None = None,
    disclosures: dict | None = None,
    statements_present: list[str] | None = None,
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
) -> dict:
    """Run presentation and consistency checks on summary figures.

    Simplified, for analysis and learning; not a complete compliance review.

    Args:
        financial_data: current-period amounts in one currency and unit. Recognised
            keys: total_assets, current_assets, non_current_assets, cash, inventory,
            receivables, total_liabilities, current_liabilities, non_current_liabilities,
            total_equity, revenue, cost_of_sales, gross_profit, profit_before_tax,
            tax_expense, net_income, operating_cash_flow, investing_cash_flow,
            financing_cash_flow, fx_effect_on_cash, net_change_in_cash, opening_cash,
            closing_cash, dividends, other_equity_movements. Costs, tax and dividends
            are entered as positive amounts.
        framework: IFRS, IND_AS, CAS, JGAAP or KIFRS.
        prior_period: same keys for the comparative period.
        disclosures: checklist answers, {item: True/False}; unanswered items are
            reported as needing manual review.
        statements_present: statements held, from balance_sheet, income_statement,
            cash_flow_statement, changes_in_equity, notes. If omitted, presence is
            inferred from the figures.
        tolerance_pct: rounding tolerance as a percentage of the larger amount.
    """
    record = resolve_framework(framework)
    if not isfinite(tolerance_pct) or tolerance_pct < 0 or tolerance_pct > 5:
        raise ValueError("tolerance_pct must be between 0 and 5")
    fd = _clean(financial_data)
    prior = _clean(prior_period)
    answers = disclosures or {}
    unknown = set(answers) - {key for key, _ in DISCLOSURE_ITEMS}
    if unknown:
        raise ValueError(f"Unknown disclosure item(s): {', '.join(sorted(unknown))}")

    extraction = "Re-check the extracted figures against the published statements"
    outcomes = {
        "PRES_01": _statements_check(fd, statements_present, record),
        "BS_01": _sum_check(fd, ("total_liabilities", "total_equity"), "total_assets",
                            "Assets = liabilities + equity", tolerance_pct,
                            "A balance sheet that does not balance points to a missing or misclassified item"),
        "BS_02": _sum_check(fd, ("current_assets", "non_current_assets"), "total_assets",
                            "Current + non-current assets", tolerance_pct, extraction),
        "BS_03": _sum_check(fd, ("current_liabilities", "non_current_liabilities"), "total_liabilities",
                            "Current + non-current liabilities", tolerance_pct, extraction),
        "IS_01": (_result("not_applicable", "Not enough data to check gross profit")
                  if not _have(fd, "revenue", "cost_of_sales", "gross_profit")
                  else _sum_check({**fd, "_neg_cos": -fd["cost_of_sales"]}, ("revenue", "_neg_cos"),
                                  "gross_profit", "Revenue - cost of sales = gross profit",
                                  tolerance_pct, extraction)),
        "IS_02": (_result("not_applicable", "Not enough data to check net income")
                  if not _have(fd, "profit_before_tax", "tax_expense", "net_income")
                  else _sum_check({**fd, "_neg_tax": -fd["tax_expense"]}, ("profit_before_tax", "_neg_tax"),
                                  "net_income", "Profit before tax - tax = net income", tolerance_pct,
                                  "Check for discontinued operations or non-controlling interests")),
        "CF_01": _sum_check(fd, ("operating_cash_flow", "investing_cash_flow", "financing_cash_flow"),
                            "net_change_in_cash", "Net change in cash", tolerance_pct,
                            "Check for exchange rate effects on cash and the sign of each cash flow",
                            optional=("fx_effect_on_cash",)),
        "CF_02": _sum_check(fd, ("opening_cash", "net_change_in_cash"), "closing_cash",
                            "Opening cash + net change = closing cash", tolerance_pct, extraction),
        "SIGN_01": _signs_check(fd),
        "SIGN_02": _components_check(fd),
        "SIGN_03": _equity_sign_check(fd),
        "COMP_01": _comparatives_check(fd, prior),
        "COMP_02": _equity_rollforward_check(fd, prior, tolerance_pct),
    }
    for i, (key, label) in enumerate(DISCLOSURE_ITEMS, 1):
        if key not in answers or answers[key] is None:
            outcome = _result("not_applicable", "Not answered: review the notes manually")
        elif answers[key]:
            outcome = _result("pass", "Confirmed as disclosed")
        else:
            outcome = _result("fail", f"Marked as not disclosed: {label[0].lower()}{label[1:]}",
                              "Request the disclosure or record why it does not apply")
        outcomes[f"DISC_{i:02d}"] = outcome

    results = [{**check, **outcomes[check["check_id"]]} for check in get_checks()]
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    not_applicable = len(results) - passed - failed
    assessed = passed + failed
    score = round(passed / assessed * 100) if assessed else 0
    blocking = [r for r in results if r["status"] == "fail" and r["severity"] == "blocking"]

    if not assessed:
        status = "insufficient_data"
    elif blocking or score < 50:
        status = "non_compliant"
    elif score < 80:
        status = "needs_attention"
    else:
        status = "compliant"

    return {
        "framework": record,
        "framework_notes": record["notes"],
        "compliance_score": score,
        "total_checks": len(results),
        "passed": passed,
        "failed": failed,
        "not_applicable": not_applicable,
        "critical_issues": [f"{r['rule']}: {r['message']}" for r in blocking],
        "warnings": [f"{r['rule']}: {r['message']}" for r in results
                     if r["status"] == "fail" and r["severity"] != "blocking"],
        "info_items": [f"{r['rule']}: {r['message']}" for r in results if r["status"] == "not_applicable"],
        "status": status,
        "results": results,
        "recommendations": _recommendations(results),
        "tolerance_pct": tolerance_pct,
        "simplified": True,
        "disclaimer": DISCLAIMER,
    }


def _recommendations(results: list[dict]) -> list[dict]:
    order = {"blocking": ("critical", 0), "warning": ("high", 1), "info": ("medium", 2)}
    failed = sorted((r for r in results if r["status"] == "fail"), key=lambda r: order[r["severity"]][1])
    recommendations = [
        {"priority": order[r["severity"]][0], "title": r["rule"],
         "description": r["message"] + (f". {r['remediation']}." if r.get("remediation") else ".")}
        for r in failed
    ]
    manual = sum(1 for r in results if r["status"] == "not_applicable")
    if manual:
        recommendations.append({
            "priority": "medium",
            "title": "Complete the manual review items",
            "description": f"{manual} check(s) could not be assessed from the data supplied.",
        })
    return recommendations[:8]
