from datetime import datetime

from tradingbot.core.engine import TradingEngine


def test_engine_initial_status():
    engine = TradingEngine()

    status = engine.status()

    assert status["running"] is False
    assert status["started_at"] is None
    assert status["mode"] == "paper_trading"


def test_engine_start():
    engine = TradingEngine()

    engine.start()

    status = engine.status()

    assert status["running"] is True
    assert isinstance(status["started_at"], datetime)
    assert status["mode"] == "paper_trading"


def test_engine_stop():
    engine = TradingEngine()

    engine.start()
    engine.stop()

    status = engine.status()

    assert status["running"] is False
