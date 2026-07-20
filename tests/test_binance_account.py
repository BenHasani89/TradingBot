from collections.abc import Callable

import httpx
import pytest

from tradingbot.execution.binance_account import BalanceSnapshot, BinanceAccountReader

_BASE_URL = "https://testnet.binance.vision"


def _account_response(balances: list[dict] | None = None) -> httpx.Response:

    return httpx.Response(
        200,
        json={
            "balances": (
                balances
                if balances is not None
                else [
                    {"asset": "BTC", "free": "0.001", "locked": "0.0"},
                    {"asset": "USDT", "free": "9985.5", "locked": "10.0"},
                ]
            )
        },
    )


def _reader(handler: Callable[[httpx.Request], httpx.Response]) -> BinanceAccountReader:

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url=_BASE_URL)
    return BinanceAccountReader(
        api_key="test-key",
        api_secret="test-secret",  # noqa: S106 - Platzhalterwert im Test, kein echtes Secret
        base_url=_BASE_URL,
        client=client,
    )


def test_credentials_are_taken_as_constructor_parameters():

    reader = _reader(lambda request: _account_response())

    assert reader._api_key == "test-key"
    assert reader._api_secret == "test-secret"  # noqa: S105 - Platzhalterwert, kein echtes Secret


# --- get_balances(): erfolgreiche Antwort / Mapping ------------------------------------------


def test_get_balances_maps_successful_response():

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/account"
        return _account_response()

    reader = _reader(handler)

    balances = reader.get_balances()

    assert len(balances) == 2
    btc = next(b for b in balances if b.asset == "BTC")
    assert isinstance(btc, BalanceSnapshot)
    assert btc.free == pytest.approx(0.001)
    assert btc.locked == pytest.approx(0.0)
    assert btc.total == pytest.approx(0.001)

    usdt = next(b for b in balances if b.asset == "USDT")
    assert usdt.free == pytest.approx(9985.5)
    assert usdt.locked == pytest.approx(10.0)
    assert usdt.total == pytest.approx(9995.5)


def test_get_balances_empty_response_returns_empty_list():

    reader = _reader(lambda request: _account_response(balances=[]))

    assert reader.get_balances() == []


# --- get_balances(): Signierung ---------------------------------------------------------------


def test_get_balances_sends_signed_request_with_timestamp_and_signature():

    def handler(request: httpx.Request) -> httpx.Response:
        assert "timestamp" in request.url.params
        assert "signature" in request.url.params
        # HMAC-SHA256-Hex-Digest ist immer 64 Zeichen lang.
        assert len(request.url.params["signature"]) == 64
        return _account_response()

    reader = _reader(handler)

    reader.get_balances()


# --- get_balances(): Fehlerfälle ------------------------------------------------------------


def test_get_balances_binance_error_raises_runtime_error():

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": -1021, "msg": "Timestamp outside recvWindow"})

    reader = _reader(handler)

    with pytest.raises(RuntimeError, match="Timestamp outside recvWindow"):
        reader.get_balances()


def test_get_balances_server_error_raises_safe_error_without_request_details():

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"code": -1000, "msg": "Internal error"})

    reader = _reader(handler)

    with pytest.raises(RuntimeError) as excinfo:
        reader.get_balances()

    assert not isinstance(excinfo.value, httpx.HTTPStatusError)
    message = str(excinfo.value)
    assert "signature" not in message
    assert "timestamp" not in message
    assert "/api/v3/account" not in message
    assert "500" in message


def test_get_balances_network_error_raises_clean_runtime_error_without_details():

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Verbindung fehlgeschlagen", request=request)

    reader = _reader(handler)

    with pytest.raises(RuntimeError, match="Netzwerkfehler") as excinfo:
        reader.get_balances()

    message = str(excinfo.value)
    assert "signature" not in message
    assert "timestamp" not in message


# --- get_balances(): ungültige Antwort ---------------------------------------------------------


def test_get_balances_missing_asset_field_raises_clean_runtime_error():

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"balances": [{"free": "0.1", "locked": "0.0"}]})

    reader = _reader(handler)

    with pytest.raises(RuntimeError, match="unerwartetes Antwortformat"):
        reader.get_balances()


def test_get_balances_non_numeric_free_field_raises_clean_runtime_error():

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"balances": [{"asset": "BTC", "free": "keine-zahl", "locked": "0.0"}]}
        )

    reader = _reader(handler)

    with pytest.raises(RuntimeError, match="unerwartetes Antwortformat"):
        reader.get_balances()


def test_get_balances_wrong_top_level_type_raises_clean_runtime_error():
    """Antwort ist gültiges JSON, aber kein Objekt mit 'balances' (z. B.
    eine rohe Liste) - .get() auf einer Liste würde einen rohen
    AttributeError werfen, der ebenfalls sauber übersetzt werden muss."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["unerwartet"])

    reader = _reader(handler)

    with pytest.raises(RuntimeError, match="unerwartetes Antwortformat"):
        reader.get_balances()


def test_get_balances_invalid_json_raises_clean_runtime_error():

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"kein json")

    reader = _reader(handler)

    with pytest.raises(RuntimeError, match="unerwartetes Antwortformat"):
        reader.get_balances()


# --- close() --------------------------------------------------------------------------------


def test_close_closes_underlying_http_client():

    reader = _reader(lambda request: _account_response())

    reader.close()

    assert reader._client.is_closed
