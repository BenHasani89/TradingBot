"""Portfolio-bezogene Laufzeit-Sicherheitsprüfungen (Risk Guard).

Ergänzt den signalbasierten `RiskManager` um zustandsbehaftete,
portfolio-weite Prüfungen (Daily Loss Limit, Maximum Drawdown, Maximum
Exposure, Kill-Switch). Bewusst unabhängig von `TradingOrchestrator` und den
Backtest-Engines - gedacht für den Aufruf durch eine künftige
Scheduler-Schicht, vor `TradingOrchestrator.run_cycle()`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from tradingbot.portfolio.models import PortfolioStatus
from tradingbot.risk.risk_state import RiskState


@dataclass
class RiskGuardResult:
    """Ergebnis einer Portfolio-Risikoprüfung durch `PortfolioRiskGuard`."""

    approved: bool
    reason: str


class PortfolioRiskGuard:
    """Prüft ein Portfolio gegen konfigurierte Laufzeit-Sicherheitslimits.

    Hält den zugehörigen `RiskState`; Laden/Speichern über ein
    `RiskStateRepository` ist Aufgabe des Aufrufers - der Guard selbst kennt
    keine Persistenz. `prices` wird bei jeder Prüfung übergeben, keine
    eigene Anbindung an `MarketDataStore`, `DataProvider` oder `Broker`.
    """

    def __init__(
        self,
        state: RiskState,
        max_daily_loss_percent: float,
        max_drawdown_percent: float,
        max_exposure_percent: float,
        max_exposure_per_asset_percent: float,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._state = state
        self._max_daily_loss_percent = max_daily_loss_percent
        self._max_drawdown_percent = max_drawdown_percent
        self._max_exposure_percent = max_exposure_percent
        self._max_exposure_per_asset_percent = max_exposure_per_asset_percent
        self._now = now

    @property
    def state(self) -> RiskState:
        """Aktueller Risk-Zustand (für die Persistierung durch den Aufrufer)."""

        return self._state

    def check(
        self,
        portfolio_status: PortfolioStatus,
        prices: dict[str, float],
    ) -> RiskGuardResult:
        """Prüft den aktuellen Portfolio-Zustand gegen alle Limits.

        Reihenfolge: Tageswechsel erkennen -> Kill-Switch -> Maximum
        Drawdown -> Daily-Loss-Blockierung -> Maximum Exposure. `state`
        wird dabei unabhängig vom Ergebnis aktualisiert (Tagesstart,
        Peak-Equity) - der Aufrufer ist für die Persistierung des
        aktualisierten Zustands verantwortlich.
        """

        current_equity = portfolio_status.total_value(prices)
        self._handle_day_rollover(current_equity)

        if self._state.kill_switch_active:
            return RiskGuardResult(
                approved=False,
                reason=f"Kill-Switch aktiv: {self._state.kill_switch_reason}",
            )

        drawdown_result = self._check_drawdown(current_equity)
        if drawdown_result is not None:
            return drawdown_result

        if self._state.daily_loss_blocked:
            return RiskGuardResult(
                approved=False,
                reason=f"Daily Loss Limit aktiv: {self._state.daily_loss_reason}",
            )

        daily_loss_result = self._check_daily_loss(current_equity)
        if daily_loss_result is not None:
            return daily_loss_result

        exposure_result = self._check_exposure(portfolio_status, prices)
        if exposure_result is not None:
            return exposure_result

        return RiskGuardResult(approved=True, reason="Alle Risikolimits eingehalten")

    def trigger_kill_switch(self, reason: str) -> None:
        """Löst den permanenten Kill-Switch manuell aus."""

        self._state.kill_switch_active = True
        self._state.kill_switch_reason = reason

    def reset_kill_switch(self) -> None:
        """Setzt den Kill-Switch zurück - ausschliesslich manuell möglich,
        kein automatischer Reset (z. B. nicht beim Tageswechsel)."""

        self._state.kill_switch_active = False
        self._state.kill_switch_reason = None

    def _handle_day_rollover(self, current_equity: float) -> None:
        """Erkennt einen neuen Handelstag und setzt die Tagesstart-Werte
        sowie eine aktive Daily-Loss-Blockierung zurück. `peak_equity` und
        `kill_switch_active` bleiben davon unberührt (Drawdown ist ein
        strukturelles, nicht tagesbezogenes Risiko)."""

        today = self._now().date()
        if today == self._state.day_start_date:
            return

        self._state.day_start_date = today
        self._state.day_start_equity = current_equity
        self._state.daily_loss_blocked = False
        self._state.daily_loss_reason = None

    def _check_drawdown(self, current_equity: float) -> RiskGuardResult | None:
        self._state.peak_equity = max(self._state.peak_equity, current_equity)
        if self._state.peak_equity <= 0:
            return None

        drawdown_percent = (
            (self._state.peak_equity - current_equity) / self._state.peak_equity * 100
        )
        if drawdown_percent <= self._max_drawdown_percent:
            return None

        reason = (
            f"Max Drawdown überschritten: {drawdown_percent:.2f}% "
            f"(Limit {self._max_drawdown_percent:.2f}%)"
        )
        self.trigger_kill_switch(reason)
        return RiskGuardResult(approved=False, reason=reason)

    def _check_daily_loss(self, current_equity: float) -> RiskGuardResult | None:
        if self._state.day_start_equity <= 0:
            return None

        loss_percent = (
            (self._state.day_start_equity - current_equity)
            / self._state.day_start_equity
            * 100
        )
        if loss_percent <= self._max_daily_loss_percent:
            return None

        reason = (
            f"Daily Loss Limit überschritten: {loss_percent:.2f}% "
            f"(Limit {self._max_daily_loss_percent:.2f}%)"
        )
        self._state.daily_loss_blocked = True
        self._state.daily_loss_reason = reason
        return RiskGuardResult(approved=False, reason=reason)

    def _check_exposure(
        self,
        portfolio_status: PortfolioStatus,
        prices: dict[str, float],
    ) -> RiskGuardResult | None:
        total_value = portfolio_status.total_value(prices)
        if total_value <= 0:
            return None

        for position in portfolio_status.positions:
            if position.symbol not in prices:
                continue
            asset_percent = position.value(prices[position.symbol]) / total_value * 100
            if asset_percent > self._max_exposure_per_asset_percent:
                return RiskGuardResult(
                    approved=False,
                    reason=(
                        f"Max Exposure je Asset überschritten: {position.symbol} "
                        f"{asset_percent:.2f}% "
                        f"(Limit {self._max_exposure_per_asset_percent:.2f}%)"
                    ),
                )

        invested_value = sum(
            position.value(prices[position.symbol])
            for position in portfolio_status.positions
            if position.symbol in prices
        )
        exposure_percent = invested_value / total_value * 100
        if exposure_percent > self._max_exposure_percent:
            return RiskGuardResult(
                approved=False,
                reason=(
                    f"Max Exposure überschritten: {exposure_percent:.2f}% "
                    f"(Limit {self._max_exposure_percent:.2f}%)"
                ),
            )

        return None
