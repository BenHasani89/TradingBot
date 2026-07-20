import pytest

from tradingbot.execution.binance_account import BalanceSnapshot
from tradingbot.paper_trading.balance_reconciliation import (
    BalanceReconciler,
    BalanceReconciliationResult,
)
from tradingbot.portfolio.models import PortfolioStatus, Position


def _portfolio(capital: float, positions: list[Position] | None = None) -> PortfolioStatus:

    return PortfolioStatus(capital=capital, positions=positions if positions is not None else [])


def _position(symbol: str, quantity: float) -> Position:

    return Position(symbol=symbol, quantity=quantity, entry_price=100.0)


def _reconciler() -> BalanceReconciler:

    return BalanceReconciler()


def test_compare_identical_quantities_are_matched():

    results = _reconciler().compare(
        local_portfolio=_portfolio(capital=1000.0, positions=[_position("BTCUSDT", 0.5)]),
        balances=[
            BalanceSnapshot(asset="BTC", free=0.5, locked=0.0),
            BalanceSnapshot(asset="USDT", free=1000.0, locked=0.0),
        ],
        base_asset="BTC",
        quote_asset="USDT",
    )

    assert len(results) == 2
    btc_result = next(r for r in results if r.asset == "BTC")
    assert isinstance(btc_result, BalanceReconciliationResult)
    assert btc_result.matched is True
    assert btc_result.local_quantity == pytest.approx(0.5)
    assert btc_result.binance_quantity == pytest.approx(0.5)
    assert btc_result.difference == pytest.approx(0.0)

    usdt_result = next(r for r in results if r.asset == "USDT")
    assert usdt_result.matched is True
    assert usdt_result.local_quantity == pytest.approx(1000.0)
    assert usdt_result.binance_quantity == pytest.approx(1000.0)


def test_compare_quote_asset_uses_capital_directly():
    """Der lokale Quote-Asset-Wert stammt aus PortfolioStatus.capital,
    nicht aus positions - keine Position mit dem Quote-Asset-Symbol
    nötig."""

    results = _reconciler().compare(
        local_portfolio=_portfolio(capital=9985.5, positions=[]),
        balances=[BalanceSnapshot(asset="USDT", free=9980.0, locked=5.5)],
        base_asset="BTC",
        quote_asset="USDT",
    )

    usdt_result = next(r for r in results if r.asset == "USDT")
    assert usdt_result.local_quantity == pytest.approx(9985.5)
    assert usdt_result.binance_quantity == pytest.approx(9985.5)
    assert usdt_result.matched is True


def test_compare_base_asset_difference_is_not_matched():

    results = _reconciler().compare(
        local_portfolio=_portfolio(capital=0.0, positions=[_position("BTCUSDT", 0.5)]),
        balances=[BalanceSnapshot(asset="BTC", free=0.45, locked=0.0)],
        base_asset="BTC",
        quote_asset="USDT",
    )

    btc_result = next(r for r in results if r.asset == "BTC")
    assert btc_result.matched is False
    assert btc_result.local_quantity == pytest.approx(0.5)
    assert btc_result.binance_quantity == pytest.approx(0.45)
    assert btc_result.difference == pytest.approx(0.05)
    assert "Abweichung" in btc_result.reason


def test_compare_missing_asset_on_binance_is_not_matched():

    results = _reconciler().compare(
        local_portfolio=_portfolio(capital=0.0, positions=[_position("BTCUSDT", 0.5)]),
        balances=[],
        base_asset="BTC",
        quote_asset="USDT",
    )

    btc_result = next(r for r in results if r.asset == "BTC")
    assert btc_result.matched is False
    assert btc_result.binance_quantity == 0.0
    assert btc_result.local_quantity == pytest.approx(0.5)
    assert "nicht im Binance-Kontostand gefunden" in btc_result.reason


def test_compare_ignores_unrelated_balances():
    """balances enthält mehrere, für diese Session nicht relevante
    Assets (ETH, BNB) - compare() liefert trotzdem nur die zwei
    angefragten Ergebnisse (base_asset, quote_asset)."""

    results = _reconciler().compare(
        local_portfolio=_portfolio(capital=1000.0, positions=[_position("BTCUSDT", 0.5)]),
        balances=[
            BalanceSnapshot(asset="BTC", free=0.5, locked=0.0),
            BalanceSnapshot(asset="ETH", free=10.0, locked=0.0),
            BalanceSnapshot(asset="BNB", free=1.0, locked=0.0),
            BalanceSnapshot(asset="USDT", free=1000.0, locked=0.0),
        ],
        base_asset="BTC",
        quote_asset="USDT",
    )

    assert {r.asset for r in results} == {"BTC", "USDT"}
    assert len(results) == 2


def test_compare_zero_balance_is_matched():

    results = _reconciler().compare(
        local_portfolio=_portfolio(capital=0.0, positions=[]),
        balances=[
            BalanceSnapshot(asset="BTC", free=0.0, locked=0.0),
            BalanceSnapshot(asset="USDT", free=0.0, locked=0.0),
        ],
        base_asset="BTC",
        quote_asset="USDT",
    )

    for result in results:
        assert result.matched is True
        assert result.local_quantity == 0.0
        assert result.binance_quantity == 0.0


def test_compare_sums_multiple_local_positions_for_base_asset():

    results = _reconciler().compare(
        local_portfolio=_portfolio(
            capital=0.0, positions=[_position("BTCUSDT", 0.3), _position("BTCUSDT", 0.2)]
        ),
        balances=[BalanceSnapshot(asset="BTC", free=0.5, locked=0.0)],
        base_asset="BTC",
        quote_asset="USDT",
    )

    btc_result = next(r for r in results if r.asset == "BTC")
    assert btc_result.matched is True
    assert btc_result.local_quantity == pytest.approx(0.5)


def test_compare_includes_locked_balance_in_binance_quantity():

    results = _reconciler().compare(
        local_portfolio=_portfolio(capital=0.0, positions=[_position("BTCUSDT", 0.5)]),
        balances=[BalanceSnapshot(asset="BTC", free=0.3, locked=0.2)],
        base_asset="BTC",
        quote_asset="USDT",
    )

    btc_result = next(r for r in results if r.asset == "BTC")
    assert btc_result.binance_quantity == pytest.approx(0.5)
    assert btc_result.matched is True


def test_compare_does_not_mutate_inputs():
    """Reine Analyse - keine Seiteneffekte auf die übergebenen Objekte."""

    portfolio = _portfolio(capital=1000.0, positions=[_position("BTCUSDT", 0.5)])
    balances = [
        BalanceSnapshot(asset="BTC", free=0.5, locked=0.0),
        BalanceSnapshot(asset="USDT", free=1000.0, locked=0.0),
    ]

    _reconciler().compare(
        local_portfolio=portfolio, balances=balances, base_asset="BTC", quote_asset="USDT"
    )

    assert portfolio.capital == 1000.0
    assert portfolio.positions[0].quantity == 0.5
    assert balances[0].free == 0.5
