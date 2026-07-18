"""Mock Live Broker: simuliert realistische Broker-Fehlerzustände (Timeout,
Reject, UNKNOWN, Partial Fill, verspätete Statusänderung) ohne echte
Netzwerk-/Börsenanbindung.

Kein Backtest-/Research-Werkzeug (dafür bleibt `PaperBroker` zuständig) -
dient ausschliesslich dem gezielten Härten von OrderManager, Reconciliation
und der Paper-Trading-Runtime gegen Fehlerfälle, die ein echter LiveBroker
verursachen könnte, bevor echtes Geld beteiligt ist. Aktuell ein internes
Entwicklungs-/Testwerkzeug - keine CLI-/Composition-Anbindung in dieser
Phase.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from tradingbot.execution.broker import Broker
from tradingbot.execution.models import ExecutionResult, ExecutionStatus, Order


class MockOutcome(Enum):
    """Was `MockLiveBroker.execute()` für eine Order tun soll."""

    SUCCESS = "success"
    FAILED = "failed"
    UNKNOWN = "unknown"
    TIMEOUT = "timeout"
    PARTIAL_FILL = "partial_fill"


@dataclass
class MockExecutionScenario:
    """Beschreibt, wie `MockLiveBroker` eine einzelne Order behandeln soll.

    `execute_outcome` bestimmt, was `execute()` liefert (oder ob es wirft
    - bei `TIMEOUT`). `filled_quantity` ist nur bei `PARTIAL_FILL`
    relevant. `status_sequence` (optional) bestimmt, was aufeinander-
    folgende `get_order_status()`-Aufrufe liefern - unabhängig von
    `execute_outcome`, damit auch nach einem simulierten Timeout eine
    spätere Aufklärung testbar ist: jeder Aufruf konsumiert den nächsten
    Eintrag der Liste, danach bleibt der letzte Wert stabil. Ist
    `status_sequence` leer/`None`, liefert `get_order_status()`
    durchgehend das Ergebnis von `execute()` (bzw. `None` nach einem
    Timeout, da dann nie ein `ExecutionResult` existierte).
    """

    execute_outcome: MockOutcome
    filled_quantity: float | None = None
    status_sequence: list[ExecutionStatus] | None = None


ScenarioProvider = Callable[[Order], MockExecutionScenario]


class MockLiveBroker(Broker):
    """Simuliert Broker-Verhalten über eine injizierbare Szenario-Funktion
    (`scenario_provider`) statt über Boolean-Konstruktor-Flags - erlaubt
    pro Order individuell festgelegtes Verhalten, wie es ein echter
    Fehlerfall-Test braucht.
    """

    def __init__(self, scenario_provider: ScenarioProvider) -> None:
        self._scenario_provider = scenario_provider
        self._orders: dict[str, Order] = {}
        self._results: dict[str, ExecutionResult] = {}
        self._pending_status_sequences: dict[str, list[ExecutionStatus]] = {}

    def execute(self, order: Order) -> ExecutionResult:
        """Führt `order` gemäss des vom `scenario_provider` gelieferten
        `MockExecutionScenario` aus.

        `order` und ein evtl. konfiguriertes `status_sequence` werden vor
        der Fallunterscheidung erfasst, damit auch eine `TIMEOUT`-Order
        (kein `ExecutionResult`, `execute()` wirft) später über
        `get_order_status()` eine simulierte Aufklärung liefern kann.
        """

        scenario = self._scenario_provider(order)
        self._orders[order.client_order_id] = order

        if scenario.status_sequence:
            self._pending_status_sequences[order.client_order_id] = list(
                scenario.status_sequence
            )

        if scenario.execute_outcome == MockOutcome.TIMEOUT:
            raise TimeoutError(
                f"Mock: simulierter Netzwerk-Timeout für {order.client_order_id}"
            )

        result = self._build_result(order, scenario)
        self._results[order.client_order_id] = result
        return result

    def _build_result(self, order: Order, scenario: MockExecutionScenario) -> ExecutionResult:
        if scenario.execute_outcome == MockOutcome.SUCCESS:
            return ExecutionResult(
                success=True,
                order=order,
                message="Mock: erfolgreich ausgeführt",
                fee=0.0,
                slippage=0.0,
                status=ExecutionStatus.SUCCESS,
                broker_order_id=order.client_order_id,
            )

        if scenario.execute_outcome == MockOutcome.FAILED:
            return ExecutionResult(
                success=False,
                order=order,
                message="Mock: Order abgelehnt",
                fee=0.0,
                slippage=0.0,
                status=ExecutionStatus.FAILED,
                broker_order_id=None,
            )

        if scenario.execute_outcome == MockOutcome.PARTIAL_FILL:
            return ExecutionResult(
                success=True,
                order=order,
                message="Mock: teilweise gefüllt",
                fee=0.0,
                slippage=0.0,
                status=ExecutionStatus.SUCCESS,
                broker_order_id=order.client_order_id,
                filled_quantity=scenario.filled_quantity,
            )

        # MockOutcome.UNKNOWN
        return ExecutionResult(
            success=False,
            order=order,
            message="Mock: Ausgang unklar",
            fee=0.0,
            slippage=0.0,
            status=ExecutionStatus.UNKNOWN,
            broker_order_id=None,
        )

    def get_order_status(self, client_order_id: str) -> ExecutionResult | None:
        """Liefert den aktuellen Status - konsumiert bei konfiguriertem
        `status_sequence` einen Eintrag pro Aufruf (siehe
        `MockExecutionScenario`), sonst das zuletzt bekannte Ergebnis
        (`None`, falls `client_order_id` nie ausgeführt wurde bzw. nur
        ein `TIMEOUT` ohne Ergebnis vorliegt).
        """

        sequence = self._pending_status_sequences.get(client_order_id)
        if sequence:
            next_status = sequence.pop(0)
            order = self._orders[client_order_id]
            result = ExecutionResult(
                success=next_status == ExecutionStatus.SUCCESS,
                order=order,
                message="Mock: verspätete Statusänderung",
                fee=0.0,
                slippage=0.0,
                status=next_status,
                broker_order_id=(
                    client_order_id if next_status == ExecutionStatus.SUCCESS else None
                ),
            )
            self._results[client_order_id] = result
            if not sequence:
                del self._pending_status_sequences[client_order_id]

        return self._results.get(client_order_id)
