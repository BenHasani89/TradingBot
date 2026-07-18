from datetime import UTC, date, datetime

import pytest

from tradingbot.portfolio.models import PortfolioStatus, Position
from tradingbot.risk.risk_state import RiskState
from tradingbot.risk.runtime_limits import PortfolioRiskGuard


class _Clock:
    """Testbarer Zeitgeber - `now` lässt sich zwischen Aufrufen umstellen."""

    def __init__(self, current: datetime):
        self.current = current

    def __call__(self) -> datetime:
        return self.current


def _guard(
    state: RiskState,
    clock: _Clock,
    max_daily_loss_percent: float = 5.0,
    max_drawdown_percent: float = 20.0,
    max_exposure_percent: float = 80.0,
    max_exposure_per_asset_percent: float = 30.0,
) -> PortfolioRiskGuard:

    return PortfolioRiskGuard(
        state=state,
        max_daily_loss_percent=max_daily_loss_percent,
        max_drawdown_percent=max_drawdown_percent,
        max_exposure_percent=max_exposure_percent,
        max_exposure_per_asset_percent=max_exposure_per_asset_percent,
        now=clock,
    )


def _state(day_start_equity: float = 10000.0, peak_equity: float = 10000.0) -> RiskState:

    return RiskState(
        day_start_equity=day_start_equity,
        day_start_date=date(2026, 7, 18),
        peak_equity=peak_equity,
    )


# --- Grundfall ------------------------------------------------------------------------------


def test_check_approved_when_no_limit_breached():

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    guard = _guard(_state(), clock)
    status = PortfolioStatus(capital=10000.0, positions=[])

    result = guard.check(status, prices={})

    assert result.approved is True


# --- Daily Loss Limit -------------------------------------------------------------------------


def test_daily_loss_limit_blocks_when_exceeded():

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    guard = _guard(_state(day_start_equity=10000.0), clock, max_daily_loss_percent=5.0)
    status = PortfolioStatus(capital=9400.0, positions=[])  # -6%

    result = guard.check(status, prices={})

    assert result.approved is False
    assert "Daily Loss" in result.reason
    assert guard.state.daily_loss_blocked is True
    assert guard.state.kill_switch_active is False


def test_daily_loss_blocked_stays_blocked_within_same_day_even_after_recovery():

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    guard = _guard(_state(day_start_equity=10000.0), clock, max_daily_loss_percent=5.0)

    guard.check(PortfolioStatus(capital=9400.0, positions=[]), prices={})
    result = guard.check(PortfolioStatus(capital=10000.0, positions=[]), prices={})

    assert result.approved is False
    assert "Daily Loss" in result.reason


def test_daily_loss_block_resets_on_day_rollover():

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    guard = _guard(_state(day_start_equity=10000.0), clock, max_daily_loss_percent=5.0)
    guard.check(PortfolioStatus(capital=9400.0, positions=[]), prices={})

    clock.current = datetime(2026, 7, 19, 9, tzinfo=UTC)
    result = guard.check(PortfolioStatus(capital=9500.0, positions=[]), prices={})

    assert result.approved is True
    assert guard.state.daily_loss_blocked is False
    assert guard.state.day_start_date == date(2026, 7, 19)
    assert guard.state.day_start_equity == pytest.approx(9500.0)


# --- Maximum Drawdown -------------------------------------------------------------------------


def test_drawdown_limit_triggers_permanent_kill_switch():

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    guard = _guard(_state(peak_equity=10000.0), clock, max_drawdown_percent=20.0)
    status = PortfolioStatus(capital=7500.0, positions=[])  # -25% vom Peak

    result = guard.check(status, prices={})

    assert result.approved is False
    assert "Drawdown" in result.reason
    assert guard.state.kill_switch_active is True


def test_kill_switch_survives_day_rollover_unlike_daily_loss_block():

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    guard = _guard(_state(peak_equity=10000.0), clock, max_drawdown_percent=20.0)
    guard.check(PortfolioStatus(capital=7500.0, positions=[]), prices={})

    clock.current = datetime(2026, 7, 19, 9, tzinfo=UTC)
    result = guard.check(PortfolioStatus(capital=9000.0, positions=[]), prices={})

    assert result.approved is False
    assert guard.state.kill_switch_active is True
    assert "Kill-Switch" in result.reason


def test_kill_switch_requires_manual_reset():

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    guard = _guard(
        _state(day_start_equity=7500.0, peak_equity=10000.0),
        clock,
        max_drawdown_percent=20.0,
    )
    guard.check(PortfolioStatus(capital=7500.0, positions=[]), prices={})

    guard.reset_kill_switch()

    assert guard.state.kill_switch_active is False

    # Erholt sich das Portfolio über die Drawdown-Schwelle (Peak bleibt bei
    # 10000), bleibt der Kill-Switch nach dem Reset auch inaktiv.
    result = guard.check(PortfolioStatus(capital=8500.0, positions=[]), prices={})

    assert guard.state.kill_switch_active is False
    assert result.approved is True


def test_manual_trigger_kill_switch():

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    guard = _guard(_state(), clock)

    guard.trigger_kill_switch("Manueller Stopp durch Betreiber")
    result = guard.check(PortfolioStatus(capital=10000.0, positions=[]), prices={})

    assert result.approved is False
    assert guard.state.kill_switch_reason == "Manueller Stopp durch Betreiber"


def test_kill_switch_short_circuits_before_other_checks():

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    guard = _guard(
        _state(day_start_equity=10000.0),
        clock,
        max_daily_loss_percent=5.0,
    )
    guard.trigger_kill_switch("Test")

    # Gleichzeitig auch ein Daily-Loss-Bruch - Kill-Switch muss zuerst greifen.
    result = guard.check(PortfolioStatus(capital=9000.0, positions=[]), prices={})

    assert "Kill-Switch" in result.reason


# --- Maximum Exposure -------------------------------------------------------------------------


def test_exposure_limit_blocks_when_total_invested_share_too_high():

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    guard = _guard(
        _state(day_start_equity=10000.0),
        clock,
        max_exposure_percent=80.0,
        max_exposure_per_asset_percent=50.0,
    )
    status = PortfolioStatus(
        capital=1000.0,
        positions=[
            Position(symbol="BTC", quantity=0.075, entry_price=60000.0),
            Position(symbol="ETH", quantity=1.5, entry_price=3000.0),
        ],
    )

    # BTC 45%, ETH 45% - je Asset unter dem Limit, zusammen aber 90% investiert.
    result = guard.check(status, prices={"BTC": 60000.0, "ETH": 3000.0})

    assert result.approved is False
    assert "Max Exposure überschritten" in result.reason


def test_exposure_per_asset_limit_blocks_single_concentrated_position():

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    guard = _guard(
        _state(day_start_equity=10000.0),
        clock,
        max_exposure_percent=90.0,
        max_exposure_per_asset_percent=30.0,
    )
    status = PortfolioStatus(
        capital=6000.0,
        positions=[Position(symbol="BTC", quantity=0.1, entry_price=40000.0)],
    )

    result = guard.check(status, prices={"BTC": 40000.0})  # 40% in einem Asset

    assert result.approved is False
    assert "je Asset" in result.reason


def test_exposure_check_ignores_symbols_missing_from_prices():

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    guard = _guard(_state(day_start_equity=9000.0), clock)
    status = PortfolioStatus(
        capital=9000.0,
        positions=[Position(symbol="BTC", quantity=0.1, entry_price=1000.0)],
    )

    result = guard.check(status, prices={})

    assert result.approved is True
