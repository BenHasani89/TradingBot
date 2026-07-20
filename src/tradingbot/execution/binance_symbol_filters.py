"""Binance-Spot-Handelsregeln je Symbol (`LOT_SIZE`/`NOTIONAL`), abgerufen
über den öffentlichen, unsignierten Endpunkt `GET /api/v3/exchangeInfo`.

Braucht KEINE Credentials - wie `data/binance_provider.py` ein rein
öffentlicher Endpunkt, deshalb bewusst als eigene, kleine Komponente
getrennt von `LiveBroker` gehalten statt dort mit hineinkopiert (gleiche
Trennung öffentlich/signiert wie zwischen `BinanceDataProvider` und
`LiveBroker`).

Existiert ausschliesslich, um `LiveBroker.execute()` vor Binances
`-1111 "Parameter 'quantity' has too much precision."` zu schützen: eine
aus `position_size / current_price` berechnete Menge hat i. d. R. volle
Fliesskomma-Präzision, Binance verlangt aber ein exaktes Vielfaches von
`stepSize`. Rechnet ausschliesslich mit `decimal.Decimal` (nie `float`-
Rundung) und rundet ausschliesslich ABWÄRTS (`ROUND_DOWN`) - eine Order
darf durch Rundung nie grösser werden als ursprünglich berechnet.

Filter-Ergebnisse werden pro Symbol für die Lebensdauer der Instanz
zwischengespeichert (`exchangeInfo` ändert sich innerhalb einer laufenden
Session praktisch nie) - kein `min_request_interval_seconds`-Throttle wie
bei `LiveBroker`/`BinanceDataProvider` nötig, da nach dem ersten Abruf pro
Symbol kein weiterer Netzwerk-Aufruf mehr stattfindet.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

import httpx


@dataclass
class SymbolFilters:
    """Die für die Mengenberechnung relevanten Binance-Handelsregeln
    eines Symbols."""

    step_size: Decimal
    min_qty: Decimal
    min_notional: Decimal


class BinanceSymbolFilters:
    """Rundet eine angefragte Menge auf ein gültiges `LOT_SIZE`-Vielfaches
    ab und prüft `minQty`/`minNotional`.

    `round_quantity()` liefert `(None, Grund)`, wenn die Order aus
    irgendeinem Grund NICHT gesendet werden darf - `exchangeInfo` nicht
    verfügbar, gerundete Menge unter `minQty`, oder resultierender
    Nominalwert unter `minNotional`. In allen drei Fällen entscheidet
    `LiveBroker.execute()` dann, gar keinen Request an `/api/v3/order` zu
    stellen (siehe dort).
    """

    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self._client = client if client is not None else httpx.Client(base_url=base_url)
        self._cache: dict[str, SymbolFilters] = {}

    def close(self) -> None:
        """Gibt die zugrunde liegende HTTP-Verbindung frei - Verbindungs-
        Lifecycle bleibt bewusst intern, kein Teil der `Broker`-ABC."""

        self._client.close()

    def round_quantity(
        self, symbol: str, quantity: float, price: float
    ) -> tuple[Decimal | None, str | None]:
        """Rundet `quantity` für `symbol` auf das nächste gültige
        `stepSize`-Vielfache ab (`ROUND_DOWN`, reine `Decimal`-Arithmetik).

        Gibt `(gerundete_menge, None)` bei Erfolg zurück, sonst
        `(None, Grund)`. `price` dient ausschliesslich der
        `minNotional`-Prüfung (Schätzpreis, wie bereits beim Cash-Check in
        `TradingOrchestrator` verwendet - kein Anspruch auf den späteren
        echten Fill-Preis).
        """

        filters = self._get_filters(symbol)
        if filters is None:
            return None, f"exchangeInfo für {symbol!r} nicht verfügbar"

        quantity_decimal = Decimal(str(quantity))
        steps = (quantity_decimal / filters.step_size).to_integral_value(rounding=ROUND_DOWN)
        rounded = steps * filters.step_size

        if rounded < filters.min_qty:
            return None, f"quantity {rounded} nach LOT_SIZE-Rundung unter minQty {filters.min_qty}"

        notional = rounded * Decimal(str(price))
        if notional < filters.min_notional:
            return None, f"Nominalwert {notional} unter minNotional {filters.min_notional}"

        return rounded, None

    def _get_filters(self, symbol: str) -> SymbolFilters | None:
        """Ruft `exchangeInfo` für `symbol` ab und cached das Ergebnis.
        Liefert `None` bei jedem Fehlschlag (Netzwerkfehler, HTTP-Fehler,
        unerwartetes/unvollständiges Antwortformat) - bewusst kein
        Exception-Pfad, da ein fehlender Filter für `LiveBroker.execute()`
        ausschliesslich bedeutet "Order nicht senden", kein unklarer
        Ausgang."""

        cached = self._cache.get(symbol)
        if cached is not None:
            return cached

        try:
            response = self._client.get("/api/v3/exchangeInfo", params={"symbol": symbol})
        except httpx.HTTPError:
            return None

        if response.status_code >= 400:
            return None

        try:
            data = response.json()
            symbol_entries = data.get("symbols") or []
            if not symbol_entries:
                return None

            step_size: Decimal | None = None
            min_qty: Decimal | None = None
            min_notional: Decimal | None = None
            for symbol_filter in symbol_entries[0].get("filters", []):
                filter_type = symbol_filter.get("filterType")
                if filter_type == "LOT_SIZE":
                    step_size = Decimal(symbol_filter["stepSize"])
                    min_qty = Decimal(symbol_filter["minQty"])
                elif filter_type in ("NOTIONAL", "MIN_NOTIONAL"):
                    min_notional = Decimal(symbol_filter["minNotional"])
        except (ValueError, KeyError, TypeError, ArithmeticError):
            return None

        if step_size is None or min_qty is None or min_notional is None:
            return None

        filters = SymbolFilters(step_size=step_size, min_qty=min_qty, min_notional=min_notional)
        self._cache[symbol] = filters
        return filters
