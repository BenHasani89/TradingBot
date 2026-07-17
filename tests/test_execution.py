from tradingbot.execution.broker import PaperBroker
from tradingbot.execution.models import Order


def test_paper_broker_execution():

    broker = PaperBroker()

    order = Order(
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.1,
        price=60000,
    )

    result = broker.execute(order)

    assert result.success is True
    assert len(broker.history()) == 1
    assert broker.history()[0].symbol == "BTCUSDT"
