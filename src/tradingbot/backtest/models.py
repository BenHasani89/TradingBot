"""Datenmodelle für Backtesting-Ergebnisse."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from tradingbot.core.models import TradingCycleResult


@dataclass
class EquityPoint:
    """Ein Punkt auf der Portfolio-Wert-Kurve (Equity Curve)."""

    timestamp: datetime
    total_value: float


@dataclass
class BacktestResult:
    """Ergebnis eines vollständigen Backtest-Laufs."""

    trades: int
    profit_loss: float
    performance_percent: float
    max_drawdown_percent: float
    equity_curve: list[EquityPoint]
    cycle_results: list[TradingCycleResult]
