"""Trade-Ledger: extrahiert abgeschlossene Trades aus Zyklus-Ergebnissen und
berechnet trade-basierte Kennzahlen (reine Funktionen, keine Klassen).

Ergänzt `backtest/metrics.py`, das auf der Equity-Kurve arbeitet - hier
liegt der Fokus auf einzelnen abgeschlossenen (realisierten) Trades.
"""

from __future__ import annotations

from tradingbot.core.models import TradingCycleResult
from tradingbot.portfolio.models import ClosedTrade


def extract_closed_trades(
    cycle_results: list[TradingCycleResult],
) -> list[ClosedTrade]:
    """Filtert die abgeschlossenen Trades aus einer Liste von Zyklus-Ergebnissen."""

    return [cycle.closed_trade for cycle in cycle_results if cycle.closed_trade is not None]


def win_rate_percent(trades: list[ClosedTrade]) -> float:
    """Anteil profitabler Trades in Prozent. `0.0` bei leerer Liste."""

    if not trades:
        return 0.0

    wins = sum(1 for trade in trades if trade.profit_loss > 0)
    return wins / len(trades) * 100


def average_win(trades: list[ClosedTrade]) -> float:
    """Durchschnittlicher Gewinn der profitablen Trades. `0.0` ohne Gewinne."""

    wins = [trade.profit_loss for trade in trades if trade.profit_loss > 0]
    if not wins:
        return 0.0

    return sum(wins) / len(wins)


def average_loss(trades: list[ClosedTrade]) -> float:
    """Durchschnittlicher Verlust der verlustreichen Trades (negativer Wert).
    `0.0` ohne Verluste.
    """

    losses = [trade.profit_loss for trade in trades if trade.profit_loss < 0]
    if not losses:
        return 0.0

    return sum(losses) / len(losses)


def profit_factor(trades: list[ClosedTrade]) -> float:
    """Verhältnis von Bruttogewinn zu Bruttoverlust (als Betrag).

    Gibt `float('inf')` zurück, wenn es Gewinne, aber keine Verluste gibt,
    und `0.0`, wenn es weder Gewinne noch Verluste gibt (z. B. leere Liste).
    """

    gross_profit = sum(trade.profit_loss for trade in trades if trade.profit_loss > 0)
    gross_loss = abs(sum(trade.profit_loss for trade in trades if trade.profit_loss < 0))

    if gross_loss == 0.0:
        return float("inf") if gross_profit > 0.0 else 0.0

    return gross_profit / gross_loss


def average_trade(trades: list[ClosedTrade]) -> float:
    """Durchschnittliches Ergebnis über alle abgeschlossenen Trades
    (Gewinne und Verluste zusammen). `0.0` bei leerer Liste.
    """

    if not trades:
        return 0.0

    return sum(trade.profit_loss for trade in trades) / len(trades)


def payoff_ratio(trades: list[ClosedTrade]) -> float:
    """Verhältnis von durchschnittlichem Gewinn zu durchschnittlichem
    Verlust (als Betrag) - die Trade-Ebene des Risiko/Rendite-Verhältnisses.

    Gibt `float('inf')` zurück, wenn es Gewinne, aber keine Verluste gibt,
    und `0.0`, wenn es keine Gewinne gibt.
    """

    win = average_win(trades)
    loss = average_loss(trades)

    if loss == 0.0:
        return float("inf") if win > 0.0 else 0.0

    return win / abs(loss)
