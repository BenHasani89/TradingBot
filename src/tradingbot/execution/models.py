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

    `PARTIALLY_FILLED` wird automatisch aus `ExecutionResult.filled_quantity`
    abgeleitet (siehe `derive_order_status()`) - ein `ExecutionResult(status=
    SUCCESS, filled_quantity=<Teilmenge>)` resultiert in `PARTIALLY_FILLED`,
    nicht in `FILLED`. `CANCELLED` bleibt weiterhin reine Modell-
    Vorbereitung - kein Code setzt ihn (keine `cancel_order()`-Methode,
    Market-Orders hinterlassen keinen offenen Rest im Orderbuch).
    """

    CREATED = "created"
    SUBMITTED = "submitted"
    FILLED = "filled"
    FAILED = "failed"
    UNKNOWN = "unknown"
    CANCELLED = "cancelled"
    PARTIALLY_FILLED = "partially_filled"


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

    `filled_quantity` ist `None`, wenn der Broker keine Teilausführung
    unterscheidet (z. B. `PaperBroker`/`MockLiveBroker` - "Legacy"-Fall,
    siehe `derive_order_status()`); ein numerischer Wert bedeutet, dass der
    Broker die tatsächlich gefüllte Menge kennt - `0.0` heisst "nichts
    gefüllt" (wird wie ein Fehlschlag behandelt), ein Wert kleiner als
    `order.quantity` bedeutet eine echte Teilausführung. `OrderManager`
    und `PortfolioManager`/`apply_trade()` (über `TradingOrchestrator`)
    werten dieses Feld aus - siehe `OrderStatus.PARTIALLY_FILLED`.

    `fee_asset` ist `None`, wenn der Broker keine Gebühren-Währung
    unterscheidet (z. B. `PaperBroker`/`MockLiveBroker` - "Legacy"-Fall,
    ebenso wenn ein `LiveBroker`-Ergebnis auf mehreren Fills mit
    unterschiedlichen Gebühren-Assets beruht, siehe
    `execution/live_broker.py`) - ein gesetzter Wert bedeutet, dass `fee`
    eindeutig in diesem Asset denominiert ist. `TradingOrchestrator` darf
    `fee` nur dann direkt zum Cash-Impact addieren, wenn `fee_asset is
    None` oder `fee == 0.0` ist - ein bekanntes, von `None` verschiedenes
    `fee_asset` könnte vom Quote-Asset des gehandelten Symbols abweichen
    (z. B. Base-Asset-Gebühr bei einem BUY) und würde sonst eine
    Einheiten-Vermischung in die Portfolio-Buchhaltung einführen.
    """

    success: bool
    order: Order
    message: str
    fee: float
    slippage: float
    status: ExecutionStatus = ExecutionStatus.SUCCESS
    broker_order_id: str | None = None
    filled_quantity: float | None = None
    fee_asset: str | None = None


def derive_order_status(execution_result: ExecutionResult) -> OrderStatus:
    """Leitet den `OrderStatus` aus einem `ExecutionResult` ab - einzige
    Stelle, die `filled_quantity` in einen Lifecycle-Status übersetzt.
    Gemeinsam verwendet von `OrderManager` (Statuspflege nach `execute()`)
    und `ReconciliationService` (Vergleich gegen den lokalen Status), damit
    beide garantiert dieselbe Logik anwenden.

    `ExecutionStatus.FAILED`/`UNKNOWN` übersetzen sich direkt in
    `OrderStatus.FAILED`/`UNKNOWN`, unabhängig von `filled_quantity`. Für
    `ExecutionStatus.SUCCESS`:

    - `filled_quantity is None` ("Legacy", z. B. `PaperBroker`/
      `MockLiveBroker`, die nie zwischen ganz und teilweise unterscheiden)
      -> `FILLED`, unverändertes Verhalten.
    - `filled_quantity == 0` -> `FAILED` (nichts wurde tatsächlich
      gehandelt, unabhängig vom formalen Erfolg der Anfrage).
    - `0 < filled_quantity < order.quantity` -> `PARTIALLY_FILLED`.
    - `filled_quantity >= order.quantity` -> `FILLED`.
    """

    if execution_result.status == ExecutionStatus.FAILED:
        return OrderStatus.FAILED
    if execution_result.status == ExecutionStatus.UNKNOWN:
        return OrderStatus.UNKNOWN

    filled_quantity = execution_result.filled_quantity
    if filled_quantity is None:
        return OrderStatus.FILLED
    if filled_quantity == 0:
        return OrderStatus.FAILED
    if filled_quantity < execution_result.order.quantity:
        return OrderStatus.PARTIALLY_FILLED
    return OrderStatus.FILLED
