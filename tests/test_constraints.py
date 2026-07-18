from tradingbot.portfolio_construction.constraints import PortfolioConstraints


def test_constraints_caps_overweight_asset():

    constraints = PortfolioConstraints(max_weight_per_asset=0.5)

    weights, adjustments = constraints.apply({"A": 0.7, "B": 0.3})

    assert weights == {"A": 0.5, "B": 0.3}
    assert len(adjustments) == 1
    assert adjustments[0].symbol == "A"
    assert adjustments[0].original_weight == 0.7
    assert adjustments[0].adjusted_weight == 0.5


def test_constraints_no_adjustment_when_within_limits():

    constraints = PortfolioConstraints(max_weight_per_asset=0.5)

    weights, adjustments = constraints.apply({"A": 0.4, "B": 0.3})

    assert weights == {"A": 0.4, "B": 0.3}
    assert adjustments == []


def test_constraints_default_max_weight_allows_full_allocation():

    constraints = PortfolioConstraints()

    weights, adjustments = constraints.apply({"A": 1.0})

    assert weights == {"A": 1.0}
    assert adjustments == []


def test_constraints_caps_multiple_assets_independently():

    constraints = PortfolioConstraints(max_weight_per_asset=0.4)

    weights, adjustments = constraints.apply({"A": 0.6, "B": 0.3, "C": 0.5})

    assert weights == {"A": 0.4, "B": 0.3, "C": 0.4}
    assert {a.symbol for a in adjustments} == {"A", "C"}
