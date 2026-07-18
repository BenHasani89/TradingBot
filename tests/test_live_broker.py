import pytest

from tradingbot.execution.broker import Broker
from tradingbot.execution.live_broker import LiveBroker
from tradingbot.execution.models import Order


class _FakeClock:
    """`monotonic`- und `sleep`-Ersatz für deterministische Tests: `sleep`
    lässt die simulierte Zeit tatsächlich vorrücken, wie ein echter Sleep
    es täte."""

    def __init__(self, start: float = 0.0) -> None:
        self.current = start
        self.sleep_calls: list[float] = []

    def now(self) -> float:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self.current += seconds


def _order(client_order_id: str = "order-1") -> Order:

    return Order(
        symbol="BTCUSDT", side="BUY", quantity=0.1, price=60000.0, client_order_id=client_order_id
    )


def _broker(clock: _FakeClock, min_request_interval_seconds: float = 1.0) -> LiveBroker:

    return LiveBroker(
        api_key="test-key",
        api_secret="test-secret",  # noqa: S106 - Platzhalterwert im Test, kein echtes Secret
        min_request_interval_seconds=min_request_interval_seconds,
        sleep=clock.sleep,
        monotonic=clock.now,
    )


def test_live_broker_is_a_broker():

    assert isinstance(_broker(_FakeClock()), Broker)


# --- Strukturelle Vorbereitung ohne Exchange-Anbindung ------------------------------------


def test_execute_raises_not_implemented_error():

    broker = _broker(_FakeClock())

    with pytest.raises(NotImplementedError, match="keine Exchange-Anbindung"):
        broker.execute(_order())


def test_get_order_status_raises_not_implemented_error():

    broker = _broker(_FakeClock())

    with pytest.raises(NotImplementedError, match="keine Exchange-Anbindung"):
        broker.get_order_status("order-1")


def test_credentials_are_taken_as_constructor_parameters():
    """Keine ENV-Auflösung im LiveBroker selbst - reine Übernahme der
    übergebenen Werte, damit die Klasse unabhängig vom Deployment-Kontext
    testbar bleibt (siehe cli/composition.py für die ENV-Auflösung)."""

    broker = LiveBroker(api_key="my-key", api_secret="my-secret")  # noqa: S106 - Platzhalterwert

    assert broker._api_key == "my-key"
    assert broker._api_secret == "my-secret"  # noqa: S105 - Platzhalterwert, kein echtes Secret


# --- Rate Limiting --------------------------------------------------------------------------


def test_first_call_does_not_throttle():

    clock = _FakeClock(start=0.0)
    broker = _broker(clock, min_request_interval_seconds=1.0)

    with pytest.raises(NotImplementedError):
        broker.execute(_order())

    assert clock.sleep_calls == []


def test_throttle_waits_when_calls_are_too_close_together():

    clock = _FakeClock(start=0.0)
    broker = _broker(clock, min_request_interval_seconds=1.0)

    with pytest.raises(NotImplementedError):
        broker.execute(_order("order-1"))

    clock.current = 0.3  # nur 0.3s vergangen, Minimum ist 1.0s

    with pytest.raises(NotImplementedError):
        broker.execute(_order("order-2"))

    assert clock.sleep_calls == [pytest.approx(0.7)]
    assert clock.current == pytest.approx(1.0)


def test_throttle_does_not_wait_when_enough_time_has_passed():

    clock = _FakeClock(start=0.0)
    broker = _broker(clock, min_request_interval_seconds=1.0)

    with pytest.raises(NotImplementedError):
        broker.execute(_order("order-1"))

    clock.current = 5.0  # deutlich mehr als das Minimum vergangen

    with pytest.raises(NotImplementedError):
        broker.execute(_order("order-2"))

    assert clock.sleep_calls == []


def test_throttle_applies_across_execute_and_get_order_status():

    clock = _FakeClock(start=0.0)
    broker = _broker(clock, min_request_interval_seconds=1.0)

    with pytest.raises(NotImplementedError):
        broker.execute(_order("order-1"))

    clock.current = 0.2

    with pytest.raises(NotImplementedError):
        broker.get_order_status("order-1")

    assert clock.sleep_calls == [pytest.approx(0.8)]
