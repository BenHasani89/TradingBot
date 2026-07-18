"""Modelle für Order-Ausführung."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal
from uuid import uuid4

OrderSide = Literal["BUY", "SELL"]


class ExecutionStatus(Enum):
    """Ausführungsstatus einer Order - ergänzt `ExecutionResult.success`,
    ersetzt es nicht (keine Breaking Changes an bestehendem Verhalten).

    `UNKNOWN` bildet einen Zustand ab, den `PaperBroker` nie erreicht (jede
    Ausführung ist synchron und eindeutig), der aber für einen künftigen
    `LiveBroker` zwingend nötig ist: ein Netzwerk-Timeout während der
    Ausführung lässt offen, ob die Order tatsächlich angenommen wurde -
    `success=False` allein würde das fälschlich als "sicher gescheitert"
    darstellen.
    """

    SUCCESS = "success"
    FAILED = "failed"
    UNKNOWN = "unknown"


class OrderStatus(Enum):
    """Lifecycle-Status einer Order innerhalb des `OrderManager`
    (siehe `execution/order_manager.py`).

    `CREATED` (Order-Objekt existiert, noch nicht an den Broker
    übergeben) -> `SUBMITTED` (Broker-Aufruf läuft/wurde gestartet) ->
    `FILLED`/`FAILED`/`UNKNOWN` (Endzustand, abgeleitet aus
    `ExecutionResult.status`). Eine Order, die dauerhaft bei `SUBMITTED`
    hängen bleibt (kein Folge-Save auf einen Endzustand), signalisiert
    genau den unklaren Fall, für den `UNKNOWN`/Reconciliation gedacht sind
    - z. B. wenn der Broker-Aufruf mit einer Exception abbricht, bevor ein
    `ExecutionResult` vorliegt. `CANCELLED` ist für ein künftiges
    Order-Stornierungs-Feature vorgesehen - wird in dieser Phase von
    keinem Code gesetzt (keine neue Broker-Methode, siehe
    `execution/broker.py`).
    """

    CREATED = "created"
    SUBMITTED = "submitted"
    FILLED = "filled"
    FAILED = "failed"
    UNKNOWN = "unknown"
    CANCELLED = "cancelled"


@dataclass
class Order:
    """Eine Trading-Order.

    `client_order_id` wird automatisch beim Erzeugen vergeben (UUID4) und
    identifiziert diese Order-Instanz eindeutig.

    Wichtige Einschränkung: das allein löst noch keine echte Retry-
    Idempotenz. Dafür müsste dieselbe ID über mehrere Order-*Versuche*
    hinweg (nicht nur einmalig beim Erzeugen) stabil bleiben - da
    `TradingOrchestrator` bei jedem Zyklus eine neue `Order`-Instanz baut
    (siehe `core/orchestrator.py`) und bewusst nicht geändert wird, erzeugt
    ein erneuter Versuch zwangsläufig eine neue ID. Der `OrderManager`
    (siehe `execution/order_manager.py`) erkennt darüber lediglich
    Duplikate *innerhalb* einer einzelnen `client_order_id` (z. B. bei
    einem versehentlichen doppelten `submit()`-Aufruf) - echte
    Cross-Tick-Reconciliation ("wurde diese Order wirklich ausgeführt?")
    erfordert zusätzlich eine Broker-Status-Abfrage-API, die bewusst nicht
    Teil dieser Phase ist.
    """

    symbol: str
    side: OrderSide
    quantity: float
    price: float
    client_order_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass
class ExecutionResult:
    """Ergebnis einer Order-Ausführung.

    `fee` und `slippage` sind absolute Kostenbeträge (nicht Prozentwerte),
    getrennt ausgewiesen statt im Preis versteckt - Voraussetzung für eine
    spätere Brutto/Fees/Slippage/Netto-Auswertung. Bei kostenfreier
    Ausführung sind beide `0.0`.

    `status` ergänzt `success` um einen dritten Zustand (`ExecutionStatus.
    UNKNOWN`) - `success` bleibt als bestehendes Feld unverändert, keine
    Ersetzung. `broker_order_id` ist die vom Broker (nicht vom Aufrufer)
    vergebene Kennung, `None` wenn keine vergeben wurde.
    """

    success: bool
    order: Order
    message: str
    fee: float
    slippage: float
    status: ExecutionStatus = ExecutionStatus.SUCCESS
    broker_order_id: str | None = None
