from tradingbot.risk.manager import RiskManager
from tradingbot.strategy.models import TradingSignal


def test_risk_manager_accepts_good_signal():

    manager = RiskManager(max_position_size=500)

    signal = TradingSignal(
        symbol="BTCUSDT",
        signal="BUY",
        confidence=0.8,
    )

    decision = manager.evaluate(signal)

    assert decision.approved is True
    assert decision.position_size == 500
