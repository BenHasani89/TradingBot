import pytest

from tradingbot.backtest.capital_allocation import CapitalAllocator


def test_allocation_for_splits_capital_equally():

    allocator = CapitalAllocator()

    result = allocator.allocation_for(["BTCUSDT", "ETHUSDT", "AAPL"], 9000.0)

    assert result == {"BTCUSDT": 3000.0, "ETHUSDT": 3000.0, "AAPL": 3000.0}


def test_allocation_for_single_symbol_gets_full_capital():

    allocator = CapitalAllocator()

    result = allocator.allocation_for(["BTCUSDT"], 5000.0)

    assert result == {"BTCUSDT": 5000.0}


def test_allocation_for_empty_symbols_returns_empty_dict():

    allocator = CapitalAllocator()

    assert allocator.allocation_for([], 10000.0) == {}


def test_allocation_for_sums_to_total_capital():

    allocator = CapitalAllocator()

    result = allocator.allocation_for(["A", "B", "C", "D", "E"], 10000.0)

    assert sum(result.values()) == pytest.approx(10000.0)
