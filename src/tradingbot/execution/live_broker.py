"""Live Broker: echte Anbindung an die Binance Spot API (Testnet/Produktion
je nach `base_url`).

Nur Market-Orders (siehe `execution/order_manager.py`/`core/orchestrator.py`
- kein `cancel_order()`, keine offenen/Limit-Orders). Verbindungs-Lifecycle
und Rate-Limiting bleiben bewusst `LiveBroker`-interne Implementierungs-
details, nicht Teil der `Broker`-ABC (siehe `execution/broker.py`).

Credentials werden hier bewusst NICHT aus Umgebungsvariablen gelesen - das
bleibt Aufgabe von `cli/composition.py` (dem einzigen Ort, an dem konkrete
Deployment-Details wie Secrets aufgelöst werden). `LiveBroker` nimmt sie als
fertige Konstruktorwerte entgegen und bleibt dadurch unabhängig vom
Deployment-Kontext testbar (siehe `client`-Parameter für `httpx.MockTransport`
in Tests - kein echter Netzwerkzugriff nötig).

Sicherheits-Hinweis: diese Klasse protokolliert absichtlich nichts (kein
`loguru`) - `api_key`/`api_secret`/Signaturen dürfen nie in Logs landen.
Fehlermeldungen (`ExecutionResult.message`) enthalten ausschliesslich die
von Binance zurückgegebene Fehlermeldung, nie eigene Request-Details. Aus
demselben Grund fangen `execute()`/`get_order_status()` ein `httpx.
HTTPStatusError` bei HTTP 5xx ab (siehe `_raise_safe_server_error()`) und
werfen stattdessen ein `RuntimeError` ohne Request-URL - `httpx`s eigene
Fehlermeldung enthält sonst die vollständige (bei signierten Requests:
signierte, inkl. `signature`-Query-Parameter) Request-URL, die sonst
unkontrolliert bis in Logs/Audit-Log durchgereicht würde (siehe
`PaperTradingEngine._handle_cycle_error`).

Bekannte Einschränkung: `get_order_status()` kennt eine Order nur, wenn
`execute()` sie in *derselben* `LiveBroker`-Instanz zuvor gesehen hat (rein
prozessinterne Zuordnung `client_order_id -> Order`, nicht persistiert).
Nach einem Neustart mit einer neuen Instanz liefert `get_order_status()` für
Orders aus einer früheren Instanz `None` ("Broker kennt diese Order nicht")
- das lässt `ReconciliationService` sie dennoch korrekt als Mismatch
erkennen (konservativ: im Zweifel wird blockiert, nicht durchgelassen).

Bekannte Einschränkung: Binances Order-Status-Endpunkt (`GET /api/v3/order`)
liefert keine Gebühren-Aufschlüsselung (kein `fills`-Array wie bei der
Order-Platzierung) - `get_order_status()` liefert deshalb immer `fee=0.0`.
Nur das `execute()`-Ergebnis selbst kennt die tatsächliche Gebühr.

`execute()` rundet die angefragte Menge vor dem Senden über
`BinanceSymbolFilters` auf ein gültiges `LOT_SIZE`-Vielfaches ab (reine
`Decimal`-Arithmetik, siehe `execution/binance_symbol_filters.py`) - eine
aus `position_size / current_price` berechnete Menge hat sonst volle
Fliesskomma-Präzision und wird von Binance mit `-1111 "Parameter
'quantity' has too much precision."` abgelehnt. Ist `exchangeInfo` nicht
verfügbar, die gerundete Menge unter `minQty` oder der resultierende
Nominalwert unter `minNotional`, wird gar kein Request an `/api/v3/order`
gestellt - `execute()` liefert stattdessen direkt ein `ExecutionResult`
mit `status=FAILED`, wie bei einer von Binance selbst abgelehnten Order.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Callable
from urllib.parse import urlencode

import httpx

from tradingbot.execution.binance_symbol_filters import BinanceSymbolFilters
from tradingbot.execution.broker import Broker
from tradingbot.execution.models import ExecutionResult, ExecutionStatus, Order

_ORDER_DOES_NOT_EXIST_CODE = -2013


class LiveBroker(Broker):
    """Binance-Spot-Anbindung (Market-Orders) über `httpx`.

    `min_request_interval_seconds` erzwingt einen Mindestabstand zwischen
    aufeinanderfolgenden Broker-Aufrufen (`execute()` und
    `get_order_status()` gemeinsam gezählt) - eine einfache, lokale
    Drossel, bewusst nicht Binance-Weight-genau (siehe Klassendocstring
    der letzten Architekturphase) - für den Handelstakt dieses Bots
    ausreichend konservativ eingestellt statt exakt nachgebildet.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str,
        min_request_interval_seconds: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        now_ms: Callable[[], int] = lambda: int(time.time() * 1000),
        client: httpx.Client | None = None,
        symbol_filters: BinanceSymbolFilters | None = None,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._min_request_interval_seconds = min_request_interval_seconds
        self._sleep = sleep
        self._monotonic = monotonic
        self._now_ms = now_ms
        self._last_request_at: float | None = None
        # Rein prozessinterne Zuordnung, keine Persistenz - siehe
        # Einschränkungs-Hinweis im Moduldocstring.
        self._orders_by_client_order_id: dict[str, Order] = {}
        self._client = (
            client
            if client is not None
            else httpx.Client(base_url=base_url, headers={"X-MBX-APIKEY": api_key})
        )
        # Nur im LIVE-Build relevant (siehe Moduldocstring) - Default
        # konstruiert dieselbe base_url wie oben, ausschliesslich für
        # Tests explizit injizierbar (analog zum `client`-Parameter).
        self._symbol_filters = (
            symbol_filters
            if symbol_filters is not None
            else BinanceSymbolFilters(base_url=base_url)
        )
        # Einmaliger Zeit-Abgleich, ausschliesslich beim Konstruktor (siehe
        # Klassendocstring) - kein laufender Re-Sync. Schlägt der Abgleich
        # fehl, propagiert die Exception unverändert (fail fast: ohne
        # funktionierende Verbindung ist der Broker ohnehin nicht nutzbar).
        self._server_time_offset_ms = self._sync_server_time()

    def close(self) -> None:
        """Gibt die zugrunde liegende HTTP-Verbindung frei - Verbindungs-
        Lifecycle bleibt bewusst `LiveBroker`-intern, kein Teil der
        `Broker`-ABC."""

        self._client.close()
        self._symbol_filters.close()

    def _throttle(self) -> None:
        """Wartet, falls nötig, bis seit dem letzten Aufruf mindestens
        `min_request_interval_seconds` vergangen sind."""

        now = self._monotonic()
        if self._last_request_at is not None:
            elapsed = now - self._last_request_at
            remaining = self._min_request_interval_seconds - elapsed
            if remaining > 0:
                self._sleep(remaining)
                now = self._monotonic()
        self._last_request_at = now

    def _signed(self, params: dict) -> dict:
        query = urlencode(params)
        signature = hmac.new(
            self._api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return {**params, "signature": signature}

    def _request(self, method: str, path: str, params: dict, signed: bool) -> httpx.Response:
        self._throttle()

        request_params = dict(params)
        if signed:
            request_params["timestamp"] = self._now_ms() + self._server_time_offset_ms
            request_params = self._signed(request_params)

        return self._client.request(method, path, params=request_params)

    def _sync_server_time(self) -> int:
        """Ermittelt den Offset zwischen lokaler Uhr und Binance-
        Serverzeit - notwendig, weil signierte Requests einen Zeitstempel
        innerhalb einer Toleranz verlangen und bei Uhr-Drift sonst
        durchgängig fehlschlagen würden."""

        local_before = self._now_ms()
        response = self._request("GET", "/api/v3/time", {}, signed=False)
        response.raise_for_status()
        server_time = int(response.json()["serverTime"])
        return server_time - local_before

    def _raise_safe_server_error(self, response: httpx.Response) -> None:
        """Wandelt einen HTTP-5xx-Server-Fehler in ein `RuntimeError` ohne
        Request-Details um.

        `httpx.HTTPStatusError` (aus `response.raise_for_status()`) enthält
        in seiner Meldung standardmässig die vollständige Request-URL -
        bei `execute()`/`get_order_status()` ist das eine *signierte* URL
        (inkl. `signature`-Query-Parameter, siehe `_signed()`). Diese darf
        nie unverändert weitergereicht werden, da sie sonst über den
        generischen Fehlerpfad (`PaperTradingEngine._handle_cycle_error`)
        geloggt und im Audit-Log persistiert würde. Nur der HTTP-Status-Code
        wird übernommen, der Response-Body wird bewusst nicht geparst (bei
        einem 5xx nicht zwingend JSON, z. B. bei einem Gateway-Fehler)."""

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            raise RuntimeError(
                f"Binance: Serverfehler (HTTP {response.status_code}) - Ausgang unklar."
            ) from None

    def execute(self, order: Order) -> ExecutionResult:
        """Platziert eine Market-Order.

        Rundet `order.quantity` zuerst über `BinanceSymbolFilters` auf ein
        gültiges `LOT_SIZE`-Vielfaches ab (siehe Moduldocstring). Ist das
        nicht möglich (`exchangeInfo` nicht verfügbar, gerundete Menge
        unter `minQty`, Nominalwert unter `minNotional`), wird gar kein
        Request an `/api/v3/order` gestellt - `ExecutionResult` mit
        `status=FAILED` wie bei einer von Binance selbst abgelehnten
        Order, kein Ausnahmefall.

        Eine von Binance definitiv abgelehnte Order (HTTP 4xx mit
        Fehler-Payload, z. B. unzureichendes Guthaben) liefert ebenfalls
        ein `ExecutionResult` mit `status=FAILED` - kein Ausnahmefall. Ein
        Server-/Netzwerkfehler (5xx, Verbindungsabbruch) propagiert
        dagegen als Exception (Ausgang unklar, siehe `OrderManager`).
        """

        rounded_quantity, reject_reason = self._symbol_filters.round_quantity(
            order.symbol, order.quantity, order.price
        )
        if rounded_quantity is None:
            return ExecutionResult(
                success=False,
                order=order,
                message=f"Binance: {reject_reason} - Order nicht gesendet.",
                fee=0.0,
                slippage=0.0,
                status=ExecutionStatus.FAILED,
                filled_quantity=0.0,
            )

        order = Order(
            symbol=order.symbol,
            side=order.side,
            quantity=float(rounded_quantity),
            price=order.price,
            client_order_id=order.client_order_id,
        )

        self._orders_by_client_order_id[order.client_order_id] = order

        response = self._request(
            "POST",
            "/api/v3/order",
            {
                "symbol": order.symbol,
                "side": order.side,
                "type": "MARKET",
                "quantity": str(rounded_quantity),
                "newClientOrderId": order.client_order_id,
                "newOrderRespType": "FULL",
            },
            signed=True,
        )

        if response.status_code >= 500:
            self._raise_safe_server_error(response)
        if response.status_code >= 400:
            error = response.json()
            return ExecutionResult(
                success=False,
                order=order,
                message=(
                    f"Binance: {error.get('msg', 'Order abgelehnt')} "
                    f"(code {error.get('code')})"
                ),
                fee=0.0,
                slippage=0.0,
                status=ExecutionStatus.FAILED,
                filled_quantity=0.0,
            )

        return self._execution_result_from_order_response(
            order, response.json(), include_fills=True
        )

    def get_order_status(self, client_order_id: str) -> ExecutionResult | None:
        """Fragt den aktuellen Status einer zuvor über `execute()`
        gesehenen Order ab. `None`, wenn diese `client_order_id` dieser
        `LiveBroker`-Instanz unbekannt ist (siehe Einschränkungs-Hinweis
        im Moduldocstring) oder Binance sie nicht kennt (Fehlercode
        -2013)."""

        original_order = self._orders_by_client_order_id.get(client_order_id)
        if original_order is None:
            return None

        response = self._request(
            "GET",
            "/api/v3/order",
            {"symbol": original_order.symbol, "origClientOrderId": client_order_id},
            signed=True,
        )

        if response.status_code >= 500:
            self._raise_safe_server_error(response)
        if response.status_code >= 400:
            error = response.json()
            if error.get("code") == _ORDER_DOES_NOT_EXIST_CODE:
                return None
            raise RuntimeError(
                f"Binance: {error.get('msg', 'Unbekannter Fehler')} (code {error.get('code')})"
            )

        return self._execution_result_from_order_response(
            original_order, response.json(), include_fills=False
        )

    def _execution_result_from_order_response(
        self, order: Order, data: dict, include_fills: bool
    ) -> ExecutionResult:
        """Übersetzt eine Binance-Order-Antwort (von `execute()` oder
        `get_order_status()`) in ein `ExecutionResult`.

        `avg_price` wird aus `cummulativeQuoteQty / executedQty` gebildet
        (funktioniert für beide Endpunkte identisch) statt aus dem
        `fills`-Array, das nur bei der Order-Platzierung vorliegt.
        """

        executed_qty = float(data.get("executedQty", 0.0))
        cumulative_quote_qty = float(data.get("cummulativeQuoteQty", 0.0))
        avg_price = cumulative_quote_qty / executed_qty if executed_qty > 0 else order.price
        binance_status = data.get("status", "")
        broker_order_id = str(data["orderId"]) if "orderId" in data else None

        fee = 0.0
        if include_fills:
            fee = sum(float(fill.get("commission", 0.0)) for fill in data.get("fills", []))

        slippage = abs(avg_price - order.price) * executed_qty

        filled_order = Order(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=avg_price,
            client_order_id=order.client_order_id,
        )

        if binance_status == "NEW":
            # Noch nicht abschliessend bearbeitet - ehrlich als unklar
            # melden statt zu raten (siehe execution.models.ExecutionStatus).
            return ExecutionResult(
                success=False,
                order=filled_order,
                message="Binance: Order noch offen (NEW), Ausgang unklar",
                fee=fee,
                slippage=slippage,
                status=ExecutionStatus.UNKNOWN,
                broker_order_id=broker_order_id,
                filled_quantity=executed_qty,
            )

        if executed_qty <= 0:
            return ExecutionResult(
                success=False,
                order=filled_order,
                message=f"Binance: Order-Status {binance_status}, nichts gefüllt",
                fee=fee,
                slippage=0.0,
                status=ExecutionStatus.FAILED,
                broker_order_id=None,
                filled_quantity=0.0,
            )

        return ExecutionResult(
            success=True,
            order=filled_order,
            message=f"Binance: Order-Status {binance_status}",
            fee=fee,
            slippage=slippage,
            status=ExecutionStatus.SUCCESS,
            broker_order_id=broker_order_id,
            filled_quantity=executed_qty,
        )
