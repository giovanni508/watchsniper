"""Test della formula del margine."""

from app.analyzer.engine import compute_margin


def test_margin_formula() -> None:
    # Margine = (28000 - 22000) - 300 = 5700; % = 5700 / 22000 * 100
    margin = compute_margin(market_value=28000, asking_price=22000, fixed_costs=300)
    assert margin.absolute == 5700.0
    assert margin.percentage == round(5700 / 22000 * 100, 2)


def test_margin_negative_when_overpriced() -> None:
    margin = compute_margin(market_value=10000, asking_price=12000, fixed_costs=300)
    assert margin.absolute == -2300.0
    assert margin.percentage < 0


def test_margin_zero_price_does_not_divide_by_zero() -> None:
    margin = compute_margin(market_value=10000, asking_price=0, fixed_costs=300)
    assert margin.percentage == 0.0
