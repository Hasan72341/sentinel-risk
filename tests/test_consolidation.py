"""Consolidated liquidity ratios use balances net of intercompany eliminations."""
import pytest

from app.services.consolidation import consolidate_statements


def _entity(name: str) -> dict:
    return {
        "company_name": name,
        "revenue": 1000.0, "cost_of_goods_sold": 600.0, "net_income": 100.0, "ebit": 150.0,
        "total_assets": 2000.0, "total_liabilities": 800.0, "total_equity": 1200.0,
        "current_assets": 500.0, "current_liabilities": 200.0,
        "inventory": 50.0, "cash": 100.0, "accounts_receivable": 100.0,
    }


def test_current_and_quick_ratio_after_eliminations():
    result = consolidate_statements([_entity("Parent (sample)"), _entity("Subsidiary (sample)")], [100.0, 100.0])
    ratios = {r["ratio_name"]: r["value"] for r in result["ratios"]}
    # Two entities -> 5% elimination rate.
    # Receivables eliminated: 200 * 0.05 * 0.5 = 5  -> current assets 1000 - 5 = 995
    # Payables eliminated:    400 * 0.05 * 0.3 = 6  -> current liabilities 400 - 6 = 394
    assert ratios["current_ratio"] == pytest.approx(995 / 394)
    assert ratios["quick_ratio"] == pytest.approx((995 - 100) / 394)
