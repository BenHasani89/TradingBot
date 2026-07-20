from decimal import Decimal

import httpx

from tradingbot.execution.binance_symbol_filters import BinanceSymbolFilters

_BASE_URL = "https://testnet.binance.vision"


def _exchange_info_response(
    step_size: str = "0.00001000",
    min_qty: str = "0.00001000",
    min_notional: str = "5.00000000",
) -> httpx.Response:

    return httpx.Response(
        200,
        json={
            "symbols": [
                {
                    "filters": [
                        {"filterType": "LOT_SIZE", "stepSize": step_size, "minQty": min_qty},
                        {"filterType": "NOTIONAL", "minNotional": min_notional},
                    ]
                }
            ]
        },
    )


def _filters(handler) -> BinanceSymbolFilters:

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url=_BASE_URL)
    return BinanceSymbolFilters(base_url=_BASE_URL, client=client)


# --- round_quantity(): erfolgreiche Rundung ------------------------------------------------


def test_round_quantity_rounds_down_to_step_size():

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/exchangeInfo"
        assert request.url.params["symbol"] == "BTCUSDT"
        return _exchange_info_response()

    filters = _filters(handler)

    rounded, reason = filters.round_quantity("BTCUSDT", 0.123456, 60000.0)

    assert reason is None
    assert rounded == Decimal("0.12345")


def test_round_quantity_exact_reported_bug_value():
    """Der real aufgetretene Binance-Fehlerfall -1111 'Parameter quantity
    has too much precision.'"""

    filters = _filters(lambda request: _exchange_info_response())

    rounded, reason = filters.round_quantity(
        "BTCUSDT", 0.00023364667949127328, 64050.0
    )

    assert reason is None
    assert rounded == Decimal("0.00023")


def test_round_quantity_already_aligned_stays_unchanged():

    filters = _filters(lambda request: _exchange_info_response())

    rounded, reason = filters.round_quantity("BTCUSDT", 0.1, 60000.0)

    assert reason is None
    assert rounded == Decimal("0.1")


# --- round_quantity(): minQty/minNotional ---------------------------------------------------


def test_round_quantity_below_min_qty_returns_none_with_reason():

    filters = _filters(
        lambda request: _exchange_info_response(min_qty="1.00000000")
    )

    rounded, reason = filters.round_quantity("BTCUSDT", 0.5, 60000.0)

    assert rounded is None
    assert "minQty" in reason


def test_round_quantity_below_min_notional_returns_none_with_reason():

    filters = _filters(
        lambda request: _exchange_info_response(min_notional="1000000.00000000")
    )

    rounded, reason = filters.round_quantity("BTCUSDT", 0.001, 60000.0)

    assert rounded is None
    assert "minNotional" in reason


# --- round_quantity(): exchangeInfo nicht verfügbar ------------------------------------------


def test_round_quantity_http_5xx_returns_none_with_reason():

    filters = _filters(lambda request: httpx.Response(500, json={"code": -1000}))

    rounded, reason = filters.round_quantity("BTCUSDT", 0.1, 60000.0)

    assert rounded is None
    assert "exchangeInfo" in reason


def test_round_quantity_http_4xx_returns_none_with_reason():

    filters = _filters(
        lambda request: httpx.Response(400, json={"code": -1121, "msg": "Invalid symbol."})
    )

    rounded, reason = filters.round_quantity("FAKECOIN", 0.1, 60000.0)

    assert rounded is None
    assert "exchangeInfo" in reason


def test_round_quantity_network_error_returns_none_with_reason():

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Verbindung fehlgeschlagen", request=request)

    filters = _filters(handler)

    rounded, reason = filters.round_quantity("BTCUSDT", 0.1, 60000.0)

    assert rounded is None
    assert "exchangeInfo" in reason


def test_round_quantity_empty_symbols_list_returns_none_with_reason():

    filters = _filters(lambda request: httpx.Response(200, json={"symbols": []}))

    rounded, reason = filters.round_quantity("BTCUSDT", 0.1, 60000.0)

    assert rounded is None
    assert "exchangeInfo" in reason


def test_round_quantity_missing_lot_size_filter_returns_none_with_reason():

    filters = _filters(
        lambda request: httpx.Response(
            200, json={"symbols": [{"filters": [{"filterType": "NOTIONAL", "minNotional": "5.0"}]}]}
        )
    )

    rounded, reason = filters.round_quantity("BTCUSDT", 0.1, 60000.0)

    assert rounded is None
    assert "exchangeInfo" in reason


def test_round_quantity_malformed_step_size_returns_none_with_reason():

    filters = _filters(
        lambda request: httpx.Response(
            200,
            json={
                "symbols": [
                    {
                        "filters": [
                            {
                                "filterType": "LOT_SIZE",
                                "stepSize": "not-a-number",
                                "minQty": "0.00001000",
                            },
                            {"filterType": "NOTIONAL", "minNotional": "5.00000000"},
                        ]
                    }
                ]
            },
        )
    )

    rounded, reason = filters.round_quantity("BTCUSDT", 0.1, 60000.0)

    assert rounded is None
    assert "exchangeInfo" in reason


# --- Caching ---------------------------------------------------------------------------------


def test_get_filters_caches_after_first_fetch():

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return _exchange_info_response()

    filters = _filters(handler)

    filters.round_quantity("BTCUSDT", 0.1, 60000.0)
    filters.round_quantity("BTCUSDT", 0.2, 60000.0)
    filters.round_quantity("BTCUSDT", 0.3, 60000.0)

    assert call_count == 1


def test_get_filters_fetches_separately_per_symbol():

    requested_symbols: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_symbols.append(request.url.params["symbol"])
        return _exchange_info_response()

    filters = _filters(handler)

    filters.round_quantity("BTCUSDT", 0.1, 60000.0)
    filters.round_quantity("ETHUSDT", 0.1, 3000.0)
    filters.round_quantity("BTCUSDT", 0.1, 60000.0)

    assert requested_symbols == ["BTCUSDT", "ETHUSDT"]


# --- close() --------------------------------------------------------------------------------


def test_close_closes_underlying_http_client():

    filters = _filters(lambda request: _exchange_info_response())

    filters.close()

    assert filters._client.is_closed
