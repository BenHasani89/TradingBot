"""Binance Account Reader: liest schreibgeschützt den Spot-Kontostand
(`GET /api/v3/account`) - für Balance-Reconciliation, keine Order-
Funktionalität, kein `Broker`-Interface.

Signierter, privater Endpoint - derselbe HMAC-SHA256-Signing-Mechanismus
wie `execution/live_broker.py::LiveBroker`, hier bewusst separat
implementiert statt aus `LiveBroker` importiert (siehe Architektur-
Analyse "Binance Balance Reconciliation vorbereiten") - kein Refactor an
dem bereits stabilen, umfassend getesteten `LiveBroker`-Code für diese
vorbereitende, rein lesende Phase.

Credentials werden hier bewusst NICHT aus Umgebungsvariablen gelesen -
das bleibt Aufgabe von `cli/composition.py`, analog zu `LiveBroker`.

Sicherheits-Hinweis: diese Klasse protokolliert absichtlich nichts (kein
`loguru`) - `api_key`/`api_secret`/Signaturen dürfen nie in Logs landen.
Ein HTTP-5xx wird - wie bei `LiveBroker` - in eine sanitisierte
`RuntimeError` ohne Request-URL/Query-Parameter übersetzt, ein
Netzwerkfehler (Verbindungsabbruch, Timeout) ebenso in eine generische
`RuntimeError` ohne Weitergabe der rohen `httpx`-Exception-Details.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx


@dataclass
class BalanceSnapshot:
    """Der Kontostand eines einzelnen Binance-Assets."""

    asset: str
    free: float
    locked: float

    @property
    def total(self) -> float:
        """`free + locked` - als Property statt gespeichertem Feld, damit
        nie ein inkonsistenter Wert konstruiert werden kann."""

        return self.free + self.locked


class BinanceAccountReader:
    """Liest schreibgeschützt den Binance-Spot-Kontostand
    (`GET /api/v3/account`)."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._client = (
            client
            if client is not None
            else httpx.Client(base_url=base_url, headers={"X-MBX-APIKEY": api_key})
        )

    def close(self) -> None:
        """Gibt die zugrunde liegende HTTP-Verbindung frei."""

        self._client.close()

    def _signed_params(self) -> dict:
        params = {"timestamp": int(time.time() * 1000)}
        query = urlencode(params)
        signature = hmac.new(
            self._api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return {**params, "signature": signature}

    def _raise_safe_server_error(self, response: httpx.Response) -> None:
        """Wie `LiveBroker._raise_safe_server_error()` - wandelt einen
        HTTP-5xx-Fehler in eine `RuntimeError` ohne Request-URL um, da
        `httpx.HTTPStatusError` sonst die vollständige, signierte URL
        (inkl. `signature`-Query-Parameter) in seiner Meldung enthält."""

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            raise RuntimeError(
                f"Binance: Serverfehler (HTTP {response.status_code}) - Ausgang unklar."
            ) from None

    def get_balances(self) -> list[BalanceSnapshot]:
        """Fragt den aktuellen Kontostand ab.

        Wirft `RuntimeError` bei einem von Binance abgelehnten Request
        (4xx), einem Server-Fehler (5xx) oder einem Netzwerkfehler
        (Verbindungsabbruch, Timeout) - nie mit Request-URL, Query-
        Parametern oder Secrets in der Meldung. Anders als bei
        `LiveBroker.execute()` gibt es hier kein sinnvolles "stilles"
        Fehlschlag-Ergebnis: ein Kontostand ist entweder bekannt oder
        nicht, kein Teilausführungs-Konzept wie bei Orders.
        """

        try:
            response = self._client.get("/api/v3/account", params=self._signed_params())
        except httpx.HTTPError as error:
            raise RuntimeError(
                f"Binance: Netzwerkfehler bei Kontostand-Abfrage ({type(error).__name__})."
            ) from None

        if response.status_code >= 500:
            self._raise_safe_server_error(response)
        if response.status_code >= 400:
            error_payload = response.json()
            raise RuntimeError(
                f"Binance: {error_payload.get('msg', 'Unbekannter Fehler')} "
                f"(code {error_payload.get('code')})"
            )

        try:
            data = response.json()
            return [
                BalanceSnapshot(
                    asset=balance["asset"],
                    free=float(balance["free"]),
                    locked=float(balance["locked"]),
                )
                for balance in data.get("balances", [])
            ]
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            # Unerwartetes Antwortformat (kein JSON, "balances" fehlt/hat
            # falschen Typ, ein Balance-Eintrag ohne asset/free/locked) -
            # sauber als RuntimeError statt einer rohen Parsing-Exception
            # mit unklarer Fehlermeldung.
            raise RuntimeError(
                f"Binance: unerwartetes Antwortformat bei Kontostand-Abfrage "
                f"({type(error).__name__})."
            ) from None
