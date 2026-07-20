from collections.abc import Callable
from decimal import Decimal

import httpx
import pytest

from tradingbot.execution.binance_symbol_filters import BinanceSymbolFilters
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


def _default_exchange_info_handler(request: httpx.Request) -> httpx.Response:
    """Realistische `exchangeInfo`-Antwort für BTCUSDT - stepSize/minQty
    passend zur echten Binance-Testnet-Konfiguration (siehe
    binance_symbol_filters-Tests für die davon unabhängigen Unit-Tests
    der Rundungslogik selbst)."""

    return httpx.Response(
        200,
        json={
            "symbols": [
                {
                    "filters": [
                        {
                            "filterType": "LOT_SIZE",
                            "stepSize": "0.00001000",
                            "minQty": "0.00001000",
                        },
                        {"filterType": "NOTIONAL", "minNotional": "5.00000000"},
                    ]
                }
            ]
        },
    )


def _broker(
    handler: Callable[[httpx.Request], httpx.Response],
    min_request_interval_seconds: float = 0.0,
    clock: _FakeClock | None = None,
    now_ms: Callable[[], int] | None = None,
    exchange_info_handler: Callable[[httpx.Request], httpx.Response] | None = None,
) -> LiveBroker:
    """`exchangeInfo`-Aufrufe (für `BinanceSymbolFilters`) werden bereits
    hier abgefangen und beantwortet, bevor sie an `handler` gehen - so
    müssen bestehende, auf `execute()`/`get_order_status()` fokussierte
    Test-Handler `/api/v3/exchangeInfo` nicht selbst kennen."""

    clock = clock or _FakeClock()
    info_handler = exchange_info_handler or _default_exchange_info_handler

    def combined_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/exchangeInfo":
            return info_handler(request)
        return handler(request)

    client = httpx.Client(transport=httpx.MockTransport(combined_handler), base_url=_BASE_URL)
    symbol_filters = BinanceSymbolFilters(
        base_url=_BASE_URL,
        client=httpx.Client(transport=httpx.MockTransport(combined_handler), base_url=_BASE_URL),
    )
    kwargs: dict = {
        "api_key": "test-key",
        "api_secret": "test-secret",  # noqa: S106 - Platzhalterwert im Test, kein echtes Secret
        "base_url": _BASE_URL,
        "min_request_interval_seconds": min_request_interval_seconds,
        "sleep": clock.sleep,
        "monotonic": clock.now,
        "client": client,
        "symbol_filters": symbol_filters,
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
    assert broker._symbol_filters._client.is_closed


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


# --- execute(): commissionAsset / fee_asset -------------------------------------------------


def test_execute_single_fill_captures_commission_asset():

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        if request.url.path == "/api/v3/order":
            return _filled_order_response(
                fills=[
                    {
                        "price": "60000.0",
                        "qty": "0.1",
                        "commission": "0.000001",
                        "commissionAsset": "BTC",
                    }
                ],
            )
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    broker = _broker(handler)

    result = broker.execute(_order())

    assert result.fee == pytest.approx(0.000001)
    assert result.fee_asset == "BTC"


def test_execute_multiple_fills_same_asset_captures_shared_commission_asset():

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        if request.url.path == "/api/v3/order":
            return _filled_order_response(
                executed_qty="0.1",
                cumulative_quote_qty="6000.0",
                fills=[
                    {
                        "price": "59990.0",
                        "qty": "0.05",
                        "commission": "0.02",
                        "commissionAsset": "USDT",
                    },
                    {
                        "price": "60010.0",
                        "qty": "0.05",
                        "commission": "0.03",
                        "commissionAsset": "USDT",
                    },
                ],
            )
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    broker = _broker(handler)

    result = broker.execute(_order())

    assert result.fee == pytest.approx(0.05)
    assert result.fee_asset == "USDT"


def test_execute_multiple_fills_different_assets_leaves_fee_asset_none():
    """Unterschiedliche commissionAsset-Werte über mehrere Fills hinweg -
    fee_asset bleibt bewusst None statt eines willkürlich gewählten Assets,
    fee wird trotzdem als reine Summe weitergegeben."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        if request.url.path == "/api/v3/order":
            return _filled_order_response(
                executed_qty="0.1",
                cumulative_quote_qty="6000.0",
                fills=[
                    {
                        "price": "59990.0",
                        "qty": "0.05",
                        "commission": "0.00001",
                        "commissionAsset": "BNB",
                    },
                    {
                        "price": "60010.0",
                        "qty": "0.05",
                        "commission": "0.03",
                        "commissionAsset": "USDT",
                    },
                ],
            )
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    broker = _broker(handler)

    result = broker.execute(_order())

    assert result.fee == pytest.approx(0.03001)
    assert result.fee_asset is None


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


# --- execute(): Lazy Server-Time Re-Sync bei -1021 --------------------------------------------


def test_execute_resyncs_time_once_and_retries_once_after_timestamp_error():
    """Erste Order-Antwort: -1021 (Timestamp ausserhalb recvWindow) ->
    genau ein erneuter /api/v3/time-Aufruf, genau ein Retry von
    /api/v3/order -> danach Erfolg."""

    time_calls: list[int] = []
    order_calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            time_calls.append(1)
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        if request.url.path == "/api/v3/order":
            order_calls.append(1)
            if len(order_calls) == 1:
                return httpx.Response(
                    400, json={"code": -1021, "msg": "Timestamp outside recvWindow"}
                )
            return _filled_order_response()
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    broker = _broker(handler)

    result = broker.execute(_order())

    # Ein /api/v3/time-Aufruf beim Konstruktor + genau ein weiterer beim Re-Sync.
    assert len(time_calls) == 2
    assert len(order_calls) == 2
    assert result.success is True
    assert result.status == ExecutionStatus.SUCCESS


def test_execute_second_timestamp_error_after_retry_returns_failed_result():
    """Zweite Antwort ist erneut -1021 -> kein dritter Versuch, normales
    FAILED-Ergebnis statt einer Exception oder einer Endlosschleife."""

    order_calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        if request.url.path == "/api/v3/order":
            order_calls.append(1)
            return httpx.Response(
                400, json={"code": -1021, "msg": "Timestamp outside recvWindow"}
            )
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    broker = _broker(handler)

    result = broker.execute(_order())

    assert len(order_calls) == 2
    assert result.success is False
    assert result.status == ExecutionStatus.FAILED
    assert "Timestamp outside recvWindow" in result.message


def test_execute_non_timestamp_error_is_not_retried():
    """-1111 (ungültige Precision) ist kein Timestamp-Fehler -> kein
    Re-Sync, kein Retry, ein einziger /api/v3/order-Aufruf."""

    time_calls: list[int] = []
    order_calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            time_calls.append(1)
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        if request.url.path == "/api/v3/order":
            order_calls.append(1)
            return httpx.Response(
                400, json={"code": -1111, "msg": "Parameter 'quantity' has too much precision."}
            )
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    broker = _broker(handler)

    result = broker.execute(_order())

    assert len(time_calls) == 1
    assert len(order_calls) == 1
    assert result.success is False
    assert result.status == ExecutionStatus.FAILED
    assert "too much precision" in result.message


# --- get_order_status(): Lazy Server-Time Re-Sync bei -1021 -----------------------------------


def test_get_order_status_resyncs_time_once_and_retries_once_after_timestamp_error():

    time_calls: list[int] = []
    get_calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            time_calls.append(1)
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        if request.url.path == "/api/v3/order" and request.method == "POST":
            return _filled_order_response()
        if request.url.path == "/api/v3/order" and request.method == "GET":
            get_calls.append(1)
            if len(get_calls) == 1:
                return httpx.Response(
                    400, json={"code": -1021, "msg": "Timestamp outside recvWindow"}
                )
            return _filled_order_response()
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    broker = _broker(handler)
    broker.execute(_order("order-1"))

    result = broker.get_order_status("order-1")

    # Ein /api/v3/time-Aufruf beim Konstruktor + genau ein weiterer beim Re-Sync.
    assert len(time_calls) == 2
    assert len(get_calls) == 2
    assert result is not None
    assert result.success is True


def test_get_order_status_second_timestamp_error_after_retry_raises_runtime_error():

    get_calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        if request.url.path == "/api/v3/order" and request.method == "POST":
            return _filled_order_response()
        if request.url.path == "/api/v3/order" and request.method == "GET":
            get_calls.append(1)
            return httpx.Response(
                400, json={"code": -1021, "msg": "Timestamp outside recvWindow"}
            )
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    broker = _broker(handler)
    broker.execute(_order("order-1"))

    with pytest.raises(RuntimeError, match="Timestamp outside recvWindow"):
        broker.get_order_status("order-1")

    assert len(get_calls) == 2


def test_get_order_status_non_timestamp_error_is_not_retried():
    """-2013 (Order existiert nicht) bleibt unverändert per Sonderfall
    behandelt - kein Re-Sync, kein Retry, ein einziger GET-Aufruf."""

    time_calls: list[int] = []
    get_calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            time_calls.append(1)
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        if request.url.path == "/api/v3/order" and request.method == "POST":
            return _filled_order_response()
        if request.url.path == "/api/v3/order" and request.method == "GET":
            get_calls.append(1)
            return httpx.Response(400, json={"code": -2013, "msg": "Order does not exist"})
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    broker = _broker(handler)
    broker.execute(_order("order-1"))

    result = broker.get_order_status("order-1")

    assert len(time_calls) == 1
    assert len(get_calls) == 1
    assert result is None


# --- execute(): LOT_SIZE/minNotional-Rundung -------------------------------------------------


def test_execute_rounds_quantity_to_valid_lot_size_precision_before_sending():
    """Der exakte, real aufgetretene Fehlerfall: eine aus
    position_size/current_price berechnete Menge mit voller
    Fliesskomma-Präzision muss vor dem Senden auf ein gültiges
    LOT_SIZE-Vielfaches abgerundet werden (0.00023364667949127328 ->
    0.00023 bei stepSize=0.00001), sonst lehnt Binance mit
    -1111 'Parameter quantity has too much precision.' ab."""

    captured_quantity: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        if request.url.path == "/api/v3/order":
            captured_quantity.append(request.url.params["quantity"])
            return _filled_order_response(executed_qty="0.00023", cumulative_quote_qty="14.7315")
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    broker = _broker(handler)
    order = Order(
        symbol="BTCUSDT",
        side="SELL",
        quantity=0.00023364667949127328,
        price=64050.0,
        client_order_id="order-1",
    )

    result = broker.execute(order)

    assert Decimal(captured_quantity[0]) == Decimal("0.00023")
    assert result.success is True


def test_execute_exchange_info_unavailable_does_not_send_order():
    """Ist exchangeInfo nicht verfügbar, darf gar kein Request an
    /api/v3/order gestellt werden - sauberes FAILED-ExecutionResult statt
    eines unkontrollierten Sendeversuchs mit ungerundeter Menge."""

    def order_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        raise AssertionError("Darf nie aufgerufen werden, wenn exchangeInfo fehlschlägt")

    def failing_exchange_info_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"code": -1000, "msg": "Internal error"})

    broker = _broker(order_handler, exchange_info_handler=failing_exchange_info_handler)

    result = broker.execute(_order())

    assert result.success is False
    assert result.status == ExecutionStatus.FAILED
    assert result.filled_quantity == 0.0
    assert "exchangeInfo" in result.message


def test_execute_quantity_below_min_qty_after_rounding_does_not_send_order():

    def order_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        raise AssertionError("Darf nie aufgerufen werden, wenn quantity unter minQty liegt")

    def small_min_qty_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "symbols": [
                    {
                        "filters": [
                            {
                                "filterType": "LOT_SIZE",
                                "stepSize": "0.00001000",
                                "minQty": "1.00000000",
                            },
                            {"filterType": "NOTIONAL", "minNotional": "5.00000000"},
                        ]
                    }
                ]
            },
        )

    broker = _broker(order_handler, exchange_info_handler=small_min_qty_handler)

    result = broker.execute(_order())

    assert result.success is False
    assert result.status == ExecutionStatus.FAILED
    assert "minQty" in result.message


def test_execute_notional_below_min_notional_does_not_send_order():

    def order_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        raise AssertionError(
            "Darf nie aufgerufen werden, wenn der Nominalwert unter minNotional liegt"
        )

    def high_min_notional_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "symbols": [
                    {
                        "filters": [
                            {
                                "filterType": "LOT_SIZE",
                                "stepSize": "0.00001000",
                                "minQty": "0.00001000",
                            },
                            {"filterType": "NOTIONAL", "minNotional": "1000000.00000000"},
                        ]
                    }
                ]
            },
        )

    broker = _broker(order_handler, exchange_info_handler=high_min_notional_handler)

    result = broker.execute(_order())

    assert result.success is False
    assert result.status == ExecutionStatus.FAILED
    assert "minNotional" in result.message


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
    # get_order_status() liefert keine fills-Aufschlüsselung -> fee immer 0.0,
    # fee_asset immer None (analog zu fee).
    assert result.fee == 0.0
    assert result.fee_asset is None


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
