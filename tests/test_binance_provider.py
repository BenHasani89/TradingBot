from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from tradingbot.data.binance_provider import BinanceDataProvider
from tradingbot.data.models import MarketCandle

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


def _kline_row(
    open_time_ms: int = 1_700_000_000_000,
    open_price: str = "60000.0",
    high: str = "60100.0",
    low: str = "59900.0",
    close: str = "60050.0",
    volume: str = "1.5",
) -> list:

    return [
        open_time_ms,
        open_price,
        high,
        low,
        close,
        volume,
        open_time_ms + 3_600_000,
        "90000.0",
        10,
        "0.5",
        "30000.0",
        "0",
    ]


def _provider(
    handler: Callable[[httpx.Request], httpx.Response],
    min_request_interval_seconds: float = 0.0,
    clock: _FakeClock | None = None,
    now: Callable[[], datetime] | None = None,
) -> BinanceDataProvider:

    clock = clock or _FakeClock()
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url=_BASE_URL)
    kwargs: dict = {
        "base_url": _BASE_URL,
        "min_request_interval_seconds": min_request_interval_seconds,
        "sleep": clock.sleep,
        "monotonic": clock.now,
        "client": client,
    }
    if now is not None:
        kwargs["now"] = now
    return BinanceDataProvider(**kwargs)


# --- get_candles(): erfolgreiche Antwort / Mapping ------------------------------------------


def test_get_candles_maps_successful_response_to_market_candles():

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/klines"
        return httpx.Response(200, json=[_kline_row()])

    provider = _provider(handler)

    candles = provider.get_candles("BTCUSDT", "1h", 1)

    assert len(candles) == 1
    candle = candles[0]
    assert isinstance(candle, MarketCandle)
    assert candle.symbol == "BTCUSDT"
    assert candle.open == pytest.approx(60000.0)
    assert candle.high == pytest.approx(60100.0)
    assert candle.low == pytest.approx(59900.0)
    assert candle.close == pytest.approx(60050.0)
    assert candle.volume == pytest.approx(1.5)


def test_get_candles_converts_open_time_milliseconds_to_utc_datetime():

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_kline_row(open_time_ms=1_700_000_000_000)])

    provider = _provider(handler)

    candles = provider.get_candles("BTCUSDT", "1h", 1)

    assert candles[0].timestamp == datetime.fromtimestamp(1_700_000_000_000 / 1000, tz=UTC)


def test_get_candles_maps_multiple_rows_in_order():

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                _kline_row(open_time_ms=1_700_000_000_000, close="60000.0"),
                _kline_row(open_time_ms=1_700_003_600_000, close="60100.0"),
            ],
        )

    provider = _provider(handler)

    candles = provider.get_candles("BTCUSDT", "1h", 2)

    assert [c.close for c in candles] == [pytest.approx(60000.0), pytest.approx(60100.0)]


def test_get_candles_empty_response_returns_empty_list():

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    provider = _provider(handler)

    assert provider.get_candles("BTCUSDT", "1h", 10) == []


# --- get_candles(): offene (nicht abgeschlossene) Kerzen werden ausgefiltert ------------------


def test_get_candles_filters_out_currently_open_last_candle():
    """Binance liefert bei einer offenen Abfrage regelmässig die aktuell
    laufende Kerze als letztes Element - deren close ist der
    Momentanpreis, kein finaler Schlusskurs, und darf wegen
    MarketDataStores Timestamp-Dedup nie übernommen werden (siehe
    Moduldocstring von binance_provider.py)."""

    reference_now = datetime(2024, 1, 1, 12, 30, tzinfo=UTC)
    closed_open_time = int(datetime(2024, 1, 1, 11, 0, tzinfo=UTC).timestamp() * 1000)
    open_open_time = int(datetime(2024, 1, 1, 12, 0, tzinfo=UTC).timestamp() * 1000)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                _kline_row(open_time_ms=closed_open_time, close="100.0"),  # closeTime 12:00 < 12:30
                _kline_row(open_time_ms=open_open_time, close="200.0"),  # closeTime 13:00 > 12:30
            ],
        )

    provider = _provider(handler, now=lambda: reference_now)

    candles = provider.get_candles("BTCUSDT", "1h", 2)

    assert len(candles) == 1
    assert candles[0].close == pytest.approx(100.0)


def test_get_candles_keeps_all_closed_candles():

    reference_now = datetime(2024, 1, 1, 20, 0, tzinfo=UTC)
    t1 = int(datetime(2024, 1, 1, 10, 0, tzinfo=UTC).timestamp() * 1000)
    t2 = int(datetime(2024, 1, 1, 11, 0, tzinfo=UTC).timestamp() * 1000)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=[_kline_row(open_time_ms=t1), _kline_row(open_time_ms=t2)]
        )

    provider = _provider(handler, now=lambda: reference_now)

    candles = provider.get_candles("BTCUSDT", "1h", 2)

    assert len(candles) == 2


def test_get_candles_timestamp_and_mapping_unchanged_after_filtering():
    """Die Filterung darf das bestehende Mapping (Zeitstempel/OHLCV) einer
    verbleibenden, abgeschlossenen Kerze nicht verändern."""

    reference_now = datetime(2024, 1, 1, 12, 30, tzinfo=UTC)
    closed_open_time = int(datetime(2024, 1, 1, 11, 0, tzinfo=UTC).timestamp() * 1000)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                _kline_row(
                    open_time_ms=closed_open_time,
                    open_price="60000.0",
                    high="60100.0",
                    low="59900.0",
                    close="60050.0",
                    volume="1.5",
                )
            ],
        )

    provider = _provider(handler, now=lambda: reference_now)

    candles = provider.get_candles("BTCUSDT", "1h", 1)

    assert len(candles) == 1
    candle = candles[0]
    assert candle.timestamp == datetime.fromtimestamp(closed_open_time / 1000, tz=UTC)
    assert candle.open == pytest.approx(60000.0)
    assert candle.high == pytest.approx(60100.0)
    assert candle.low == pytest.approx(59900.0)
    assert candle.close == pytest.approx(60050.0)
    assert candle.volume == pytest.approx(1.5)


def test_get_candles_all_candles_open_returns_empty_list_without_padding():
    """Sind alle gelieferten Kerzen noch offen, wird eine leere Liste
    zurückgegeben - kein künstliches Auffüllen, keine Simulation."""

    reference_now = datetime(2024, 1, 1, 9, 0, tzinfo=UTC)  # vor jeder closeTime unten
    t1 = int(datetime(2024, 1, 1, 10, 0, tzinfo=UTC).timestamp() * 1000)
    t2 = int(datetime(2024, 1, 1, 11, 0, tzinfo=UTC).timestamp() * 1000)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=[_kline_row(open_time_ms=t1), _kline_row(open_time_ms=t2)]
        )

    provider = _provider(handler, now=lambda: reference_now)

    candles = provider.get_candles("BTCUSDT", "1h", 2)

    assert candles == []


# --- get_candles(): Parameter -----------------------------------------------------------------


def test_get_candles_sends_correct_query_parameters():

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["symbol"] == "ETHUSDT"
        assert request.url.params["interval"] == "4h"
        assert request.url.params["limit"] == "25"
        return httpx.Response(200, json=[])

    provider = _provider(handler)

    provider.get_candles("ETHUSDT", "4h", 25)


# --- get_candles(): Timeframe-Validierung -------------------------------------------------


def test_get_candles_unsupported_timeframe_raises_value_error_without_network_call():

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Darf für einen ungültigen Timeframe nie aufgerufen werden")

    provider = _provider(handler)

    with pytest.raises(ValueError, match="2h"):
        provider.get_candles("BTCUSDT", "2h", 10)


# --- get_candles(): Fehlerfälle ------------------------------------------------------------


def test_get_candles_unknown_symbol_raises_clear_runtime_error():

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": -1121, "msg": "Invalid symbol."})

    provider = _provider(handler)

    with pytest.raises(RuntimeError, match="Invalid symbol"):
        provider.get_candles("FAKECOIN", "1h", 10)


def test_get_candles_server_error_raises_safe_runtime_error_without_url_or_params():

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"code": -1000, "msg": "Internal error"})

    provider = _provider(handler)

    with pytest.raises(RuntimeError) as excinfo:
        provider.get_candles("BTCUSDT", "1h", 10)

    message = str(excinfo.value)
    assert "500" in message
    assert "?" not in message
    assert "symbol=" not in message


# --- Rate Limiting --------------------------------------------------------------------------


def test_first_call_does_not_throttle():

    clock = _FakeClock(start=0.0)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    provider = _provider(handler, min_request_interval_seconds=1.0, clock=clock)
    provider.get_candles("BTCUSDT", "1h", 10)

    assert clock.sleep_calls == []


def test_throttle_waits_when_calls_are_too_close_together():

    clock = _FakeClock(start=0.0)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    provider = _provider(handler, min_request_interval_seconds=1.0, clock=clock)
    provider.get_candles("BTCUSDT", "1h", 10)
    clock.current = 0.3

    provider.get_candles("BTCUSDT", "1h", 10)

    assert clock.sleep_calls == [pytest.approx(0.7)]
    assert clock.current == pytest.approx(1.0)


def test_throttle_does_not_wait_when_enough_time_has_passed():

    clock = _FakeClock(start=0.0)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    provider = _provider(handler, min_request_interval_seconds=1.0, clock=clock)
    provider.get_candles("BTCUSDT", "1h", 10)
    clock.current = 5.0

    provider.get_candles("BTCUSDT", "1h", 10)

    assert clock.sleep_calls == []


# --- close() --------------------------------------------------------------------------------


def test_close_closes_underlying_http_client():

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    provider = _provider(handler)

    provider.close()

    assert provider._client.is_closed
