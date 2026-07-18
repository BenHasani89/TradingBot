from collections.abc import Callable

import httpx
import pytest

from tradingbot.execution.broker import Broker
from tradingbot.execution.live_broker import LiveBroker
from tradingbot.execution.models import ExecutionStatus, Order

_BASE_URL = "https://testnet.binance.vision"


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


def _time_handler(server_time_ms: int = 1_700_000_000_000):
    """Handler, der ausschliesslich den Zeit-Sync-Aufruf des Konstruktors
    beantwortet - für Tests, die keine weiteren Requests erwarten."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/time"
        return httpx.Response(200, json={"serverTime": server_time_ms})

    return handler


def _filled_order_response(
    executed_qty: str = "0.1",
    cumulative_quote_qty: str = "6000.0",
    fills: list[dict] | None = None,
    order_id: int = 1,
    client_order_id: str = "order-1",
    status: str = "FILLED",
) -> httpx.Response:

    return httpx.Response(
        200,
        json={
            "symbol": "BTCUSDT",
            "orderId": order_id,
            "clientOrderId": client_order_id,
            "status": status,
            "executedQty": executed_qty,
            "cummulativeQuoteQty": cumulative_quote_qty,
            "fills": (
                fills
                if fills is not None
                else [{"price": "60000.0", "qty": executed_qty, "commission": "0.06"}]
            ),
        },
    )


def _broker(
    handler: Callable[[httpx.Request], httpx.Response],
    min_request_interval_seconds: float = 0.0,
    clock: _FakeClock | None = None,
    now_ms: Callable[[], int] | None = None,
) -> LiveBroker:

    clock = clock or _FakeClock()
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url=_BASE_URL)
    kwargs: dict = {
        "api_key": "test-key",
        "api_secret": "test-secret",  # noqa: S106 - Platzhalterwert im Test, kein echtes Secret
        "base_url": _BASE_URL,
        "min_request_interval_seconds": min_request_interval_seconds,
        "sleep": clock.sleep,
        "monotonic": clock.now,
        "client": client,
    }
    if now_ms is not None:
        kwargs["now_ms"] = now_ms
    return LiveBroker(**kwargs)


def test_live_broker_is_a_broker():

    assert isinstance(_broker(_time_handler()), Broker)


def test_credentials_are_taken_as_constructor_parameters():
    """Keine ENV-Auflösung im LiveBroker selbst - reine Übernahme der
    übergebenen Werte, damit die Klasse unabhängig vom Deployment-Kontext
    testbar bleibt (siehe cli/composition.py für die ENV-Auflösung)."""

    broker = _broker(_time_handler())

    assert broker._api_key == "test-key"
    assert broker._api_secret == "test-secret"  # noqa: S105 - Platzhalterwert, kein echtes Secret


def test_close_closes_underlying_http_client():

    broker = _broker(_time_handler())

    broker.close()

    assert broker._client.is_closed


# --- Server-Zeit-Synchronisation --------------------------------------------------------------


def test_constructor_syncs_server_time_offset_and_applies_it_to_signed_requests():

    captured_timestamps: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_700_000_005_000})
        if request.url.path == "/api/v3/order":
            captured_timestamps.append(int(request.url.params["timestamp"]))
            return _filled_order_response()
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    broker = _broker(handler, now_ms=lambda: 1_700_000_000_000)

    broker.execute(_order())

    # Offset = Server-Zeit - lokale Zeit = 5000ms, angewendet auf jeden
    # signierten Request-Zeitstempel.
    assert captured_timestamps == [1_700_000_005_000]


# --- execute() ----------------------------------------------------------------------------


def test_execute_places_market_order_and_returns_filled_result():

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        if request.url.path == "/api/v3/order":
            assert request.method == "POST"
            assert request.url.params["symbol"] == "BTCUSDT"
            assert request.url.params["side"] == "BUY"
            assert request.url.params["type"] == "MARKET"
            return _filled_order_response()
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    broker = _broker(handler)

    result = broker.execute(_order())

    assert result.success is True
    assert result.status == ExecutionStatus.SUCCESS
    assert result.filled_quantity == pytest.approx(0.1)
    assert result.fee == pytest.approx(0.06)
    assert result.broker_order_id == "1"


def test_execute_partial_fill_returns_actual_filled_quantity():

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        if request.url.path == "/api/v3/order":
            return _filled_order_response(
                executed_qty="0.04",
                cumulative_quote_qty="2400.0",
                fills=[{"price": "60000.0", "qty": "0.04", "commission": "0.024"}],
                status="PARTIALLY_FILLED",
            )
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    broker = _broker(handler)

    result = broker.execute(_order())

    assert result.success is True
    assert result.filled_quantity == pytest.approx(0.04)
    assert result.fee == pytest.approx(0.024)


def test_execute_binance_rejects_order_returns_failed_result():

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        if request.url.path == "/api/v3/order":
            return httpx.Response(
                400, json={"code": -2010, "msg": "Account has insufficient balance"}
            )
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    broker = _broker(handler)

    result = broker.execute(_order())

    assert result.success is False
    assert result.status == ExecutionStatus.FAILED
    assert result.filled_quantity == 0.0
    assert "insufficient balance" in result.message


def test_execute_server_error_raises_safe_error_without_request_details():
    """Ein HTTP-5xx muss als `RuntimeError` ohne Request-Details
    propagieren - `httpx.HTTPStatusError` (aus `raise_for_status()`) würde
    sonst die vollständige, signierte Request-URL (inkl. `signature`- und
    `timestamp`-Query-Parametern) in seiner Meldung enthalten, die sonst
    ungefiltert bis in Logs/Audit-Log durchgereicht würde."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        if request.url.path == "/api/v3/order":
            return httpx.Response(500, json={"code": -1000, "msg": "Internal error"})
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    broker = _broker(handler)

    with pytest.raises(RuntimeError) as excinfo:
        broker.execute(_order())

    assert not isinstance(excinfo.value, httpx.HTTPStatusError)
    message = str(excinfo.value)
    assert "signature" not in message
    assert "timestamp" not in message
    assert "/api/v3/order" not in message
    assert "500" in message


def test_execute_order_still_new_returns_unknown_status():

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        if request.url.path == "/api/v3/order":
            return _filled_order_response(
                executed_qty="0.0", cumulative_quote_qty="0.0", fills=[], status="NEW"
            )
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    broker = _broker(handler)

    result = broker.execute(_order())

    assert result.status == ExecutionStatus.UNKNOWN
    assert result.success is False


# --- get_order_status() --------------------------------------------------------------------


def test_get_order_status_returns_none_for_unknown_client_order_id():

    broker = _broker(_time_handler())

    assert broker.get_order_status("never-seen") is None


def test_get_order_status_after_execute_queries_binance_with_symbol_and_orig_client_order_id():

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        if request.url.path == "/api/v3/order" and request.method == "POST":
            return _filled_order_response()
        if request.url.path == "/api/v3/order" and request.method == "GET":
            assert request.url.params["symbol"] == "BTCUSDT"
            assert request.url.params["origClientOrderId"] == "order-1"
            return _filled_order_response()
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    broker = _broker(handler)
    broker.execute(_order("order-1"))

    result = broker.get_order_status("order-1")

    assert result is not None
    assert result.success is True
    # get_order_status() liefert keine fills-Aufschlüsselung -> fee immer 0.0.
    assert result.fee == 0.0


def test_get_order_status_binance_order_does_not_exist_returns_none():

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        if request.url.path == "/api/v3/order" and request.method == "POST":
            return _filled_order_response()
        if request.url.path == "/api/v3/order" and request.method == "GET":
            return httpx.Response(400, json={"code": -2013, "msg": "Order does not exist"})
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    broker = _broker(handler)
    broker.execute(_order("order-1"))

    assert broker.get_order_status("order-1") is None


def test_get_order_status_other_binance_error_raises_runtime_error():

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        if request.url.path == "/api/v3/order" and request.method == "POST":
            return _filled_order_response()
        if request.url.path == "/api/v3/order" and request.method == "GET":
            return httpx.Response(
                400, json={"code": -1021, "msg": "Timestamp outside recvWindow"}
            )
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    broker = _broker(handler)
    broker.execute(_order("order-1"))

    with pytest.raises(RuntimeError, match="Timestamp outside recvWindow"):
        broker.get_order_status("order-1")


def test_get_order_status_server_error_raises_safe_error_without_request_details():
    """Wie `test_execute_server_error_raises_safe_error_without_request_details`,
    für den `GET /api/v3/order`-Pfad (ebenfalls signiert)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        if request.url.path == "/api/v3/order" and request.method == "POST":
            return _filled_order_response()
        if request.url.path == "/api/v3/order" and request.method == "GET":
            return httpx.Response(500, json={"code": -1000, "msg": "Internal error"})
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    broker = _broker(handler)
    broker.execute(_order("order-1"))

    with pytest.raises(RuntimeError) as excinfo:
        broker.get_order_status("order-1")

    assert not isinstance(excinfo.value, httpx.HTTPStatusError)
    message = str(excinfo.value)
    assert "signature" not in message
    assert "timestamp" not in message
    assert "/api/v3/order" not in message
    assert "500" in message


# --- Rate Limiting --------------------------------------------------------------------------


def test_constructor_time_sync_does_not_throttle_since_it_is_the_first_request():

    clock = _FakeClock(start=0.0)

    _broker(_time_handler(), min_request_interval_seconds=1.0, clock=clock)

    assert clock.sleep_calls == []


def test_throttle_waits_when_calls_are_too_close_together():

    clock = _FakeClock(start=0.0)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        if request.url.path == "/api/v3/order":
            return _filled_order_response()
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    broker = _broker(handler, min_request_interval_seconds=1.0, clock=clock)
    # Konstruktor hat bereits bei t=0.0 einen Request (Zeit-Sync) ausgeführt.
    clock.current = 0.3  # nur 0.3s seither vergangen, Minimum ist 1.0s

    broker.execute(_order("order-1"))

    assert clock.sleep_calls == [pytest.approx(0.7)]
    assert clock.current == pytest.approx(1.0)


def test_throttle_does_not_wait_when_enough_time_has_passed():

    clock = _FakeClock(start=0.0)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        if request.url.path == "/api/v3/order":
            return _filled_order_response()
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    broker = _broker(handler, min_request_interval_seconds=1.0, clock=clock)
    clock.current = 5.0  # deutlich mehr als das Minimum seit dem Zeit-Sync vergangen

    broker.execute(_order("order-1"))

    assert clock.sleep_calls == []


def test_throttle_applies_across_execute_and_get_order_status():

    clock = _FakeClock(start=0.0)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        if request.url.path == "/api/v3/order":
            return _filled_order_response()
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    broker = _broker(handler, min_request_interval_seconds=1.0, clock=clock)
    clock.current = 2.0
    broker.execute(_order("order-1"))
    clock.current = 2.2  # nur 0.2s seit execute() vergangen

    broker.get_order_status("order-1")

    assert clock.sleep_calls == [pytest.approx(0.8)]
