"""Binance Spot DataProvider: liefert echte Marktdaten für
`RuntimeMode.LIVE` über den öffentlichen, unsignierten Binance-Spot-
Endpunkt `GET /api/v3/klines`.

Braucht KEINE Credentials (kein `api_key`/`api_secret`) - im Unterschied
zu `execution/live_broker.py::LiveBroker` ist dieser Endpunkt öffentlich
und unsigniert, kein Server-Zeit-Sync nötig. `base_url` muss dieselbe
Umgebung (testnet/production) verwenden wie der zugehörige `LiveBroker` -
wird deshalb in `cli/composition.py` aus derselben Quelle aufgelöst
(`_LIVE_BASE_URLS`/`TRADINGBOT_LIVE_ENVIRONMENT`), niemals unabhängig
konfiguriert.

Unterstützt ausschliesslich die bereits vorhandenen Timeframes (siehe
`data/simulated_provider.py::_TIMEFRAME_MINUTES`) - keine Erweiterung des
bestehenden `DataProvider`-Vertrags.

Fehlermeldungen enthalten nie die angefragte URL/Query-Parameter (auch
ohne Credentials unnötige Angriffsfläche) - nur HTTP-Status-Code bzw.
Binances eigene `msg`/`code`-Felder.

Binances `klines`-Antwort enthält bei einer offenen Abfrage (kein
`startTime`/`endTime`) als letztes Element regelmässig die aktuell noch
laufende, nicht abgeschlossene Kerze - ihr `close`-Wert ist der
Momentanpreis zum Abfragezeitpunkt, kein finaler Schlusskurs. Da
`MarketDataStore` über `(symbol, timestamp)` dedupliziert, würde ein
zu früh übernommener, unfertiger `close`-Wert nie mehr durch den
späteren finalen Wert ersetzt (siehe `market.py::MarketDataStore.add()`).
`get_candles()` filtert deshalb jede Kerze heraus, deren `closeTime`
noch nicht in der Vergangenheit liegt - kein künstliches Auffüllen,
liefert im Extremfall auch eine leere Liste.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime

import httpx

from tradingbot.data.models import MarketCandle
from tradingbot.data.provider import DataProvider

_SUPPORTED_TIMEFRAMES = {"1m", "5m", "15m", "1h", "4h", "1d"}


class BinanceDataProvider(DataProvider):
    """Liefert echte Binance-Spot-Kerzen über den öffentlichen
    `klines`-Endpoint.

    `min_request_interval_seconds` erzwingt denselben einfachen, lokalen
    Mindestabstand zwischen Aufrufen wie `LiveBroker` (siehe dort) -
    bewusst nicht Binance-Weight-genau, für den Abfragetakt dieses Bots
    (ein Aufruf pro Scheduler-Intervall) ausreichend konservativ.
    """

    def __init__(
        self,
        base_url: str,
        min_request_interval_seconds: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        client: httpx.Client | None = None,
    ) -> None:
        self._min_request_interval_seconds = min_request_interval_seconds
        self._sleep = sleep
        self._monotonic = monotonic
        self._now = now
        self._last_request_at: float | None = None
        self._client = client if client is not None else httpx.Client(base_url=base_url)

    def close(self) -> None:
        """Gibt die zugrunde liegende HTTP-Verbindung frei - Verbindungs-
        Lifecycle bleibt bewusst providerintern, kein Teil der
        `DataProvider`-ABC."""

        self._client.close()

    def _throttle(self) -> None:
        now = self._monotonic()
        if self._last_request_at is not None:
            elapsed = now - self._last_request_at
            remaining = self._min_request_interval_seconds - elapsed
            if remaining > 0:
                self._sleep(remaining)
                now = self._monotonic()
        self._last_request_at = now

    def get_candles(self, symbol: str, timeframe: str, limit: int) -> list[MarketCandle]:
        """Liefert die zuletzt abgeschlossenen Kerzen für `symbol` im
        `timeframe` über `GET /api/v3/klines` - fragt weiterhin `limit`
        Kerzen an, filtert danach jede Kerze heraus, deren `closeTime`
        noch nicht vergangen ist (siehe Moduldocstring). Sind dadurch
        weniger als `limit` Kerzen übrig, werden genau diese
        zurückgegeben - kein künstliches Auffüllen, im Extremfall eine
        leere Liste.

        Wirft `ValueError` bei einem nicht unterstützten `timeframe` -
        vor jedem Netzwerk-Aufruf geprüft, keine Erweiterung des
        bestehenden Interval-Sets ohne explizite Entscheidung (siehe
        Moduldocstring). Ein HTTP-5xx oder eine von Binance abgelehnte
        Anfrage (4xx, z. B. unbekanntes Symbol) wird als `RuntimeError`
        mit Status-Code bzw. Binances `msg`/`code` gemeldet - nie mit der
        angefragten URL oder Query-Parametern.
        """

        if timeframe not in _SUPPORTED_TIMEFRAMES:
            raise ValueError(
                f"Nicht unterstützter Timeframe {timeframe!r} - unterstützt werden "
                f"{sorted(_SUPPORTED_TIMEFRAMES)}."
            )

        self._throttle()

        response = self._client.get(
            "/api/v3/klines",
            params={"symbol": symbol, "interval": timeframe, "limit": limit},
        )

        if response.status_code >= 500:
            raise RuntimeError(
                f"Binance: Serverfehler (HTTP {response.status_code}) bei klines-Abfrage."
            )
        if response.status_code >= 400:
            error = response.json()
            raise RuntimeError(
                f"Binance: {error.get('msg', 'Unbekannter Fehler')} (code {error.get('code')}) "
                f"bei klines-Abfrage für {symbol!r}."
            )

        now = self._now()
        closed_rows = [row for row in response.json() if _is_closed(row, now)]
        return [_row_to_candle(symbol, row) for row in closed_rows]


def _is_closed(row: list, now: datetime) -> bool:
    """Eine Kerze gilt als abgeschlossen, wenn ihre `closeTime`
    (Index 6, Millisekunden seit Epoch) bereits in der Vergangenheit
    liegt."""

    close_time_ms = row[6]
    close_time = datetime.fromtimestamp(close_time_ms / 1000, tz=UTC)
    return close_time < now


def _row_to_candle(symbol: str, row: list) -> MarketCandle:
    """Übersetzt eine einzelne Binance-`klines`-Zeile
    (`[openTime, open, high, low, close, volume, closeTime, ...]`) in ein
    `MarketCandle`. Zeitstempel ist die Kerzen-Öffnungszeit (`openTime`,
    Millisekunden seit Epoch)."""

    open_time_ms = row[0]
    return MarketCandle(
        symbol=symbol,
        timestamp=datetime.fromtimestamp(open_time_ms / 1000, tz=UTC),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
    )
