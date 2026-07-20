"""Read-only Balance-Reconciliation: vergleicht den lokalen Portfolio-
Zustand gegen echte Binance-Kontostände (siehe
`execution/binance_account.py`) - analog zu
`paper_trading/reconciliation.py` (dort: Order-Level-Vergleich), hier auf
Asset-Ebene.

Reine Vergleichslogik: kein Binance-Zugriff, keine Persistenz, keine
Portfolio-Änderung, keine automatische Korrektur (siehe Architektur-
Analyse "Binance Balance Reconciliation vorbereiten").

`base_asset`/`quote_asset` werden bewusst als explizite Parameter
übergeben statt aus einem Handelspaar-Symbol geparst - kein Symbol-
Parsing in dieser Komponente. `compare()` nimmt den vollständigen lokalen
`PortfolioStatus` entgegen (nicht nur `positions`): `capital` liefert die
lokale Quote-Asset-Menge direkt und eindeutig, `positions` werden für
`base_asset` aufsummiert (die aktuelle Architektur kennt ohnehin nur ein
gehandeltes Symbol pro Session, siehe `RuntimeConfig`) - so ist keine
Zuordnung `Position.symbol -> Asset` nötig.

`BalanceReconciliationResult` heisst bewusst nicht `ReconciliationResult`
(der bereits in `paper_trading/reconciliation.py` für den Order-Level-
Vergleich existiert) - beide Typen sind strukturell unverwandt, ein
eigener Name vermeidet Verwechslung beim Import (analog zur bewussten
Trennung von `portfolio.models.TradeSide` und `execution.models.
OrderSide`).
"""

from __future__ import annotations

from dataclasses import dataclass

from tradingbot.execution.binance_account import BalanceSnapshot
from tradingbot.portfolio.models import PortfolioStatus

_MATCH_TOLERANCE = 1e-8


@dataclass
class BalanceReconciliationResult:
    """Ergebnis des Vergleichs für ein einzelnes Asset."""

    asset: str
    local_quantity: float
    binance_quantity: float
    matched: bool
    reason: str
    difference: float


class BalanceReconciler:
    """Vergleicht den lokalen Portfolio-Zustand gegen Binance-
    Kontostände - reine Analyse, keine Seiteneffekte."""

    def compare(
        self,
        local_portfolio: PortfolioStatus,
        balances: list[BalanceSnapshot],
        base_asset: str,
        quote_asset: str,
    ) -> list[BalanceReconciliationResult]:
        """Liefert je ein `BalanceReconciliationResult` für `base_asset` (Summe
        aller `local_portfolio.positions`-Mengen) und `quote_asset`
        (`local_portfolio.capital` direkt). Andere in `balances`
        enthaltene Assets werden ignoriert - ein echtes Binance-Konto
        führt typischerweise Dutzende, meist leere, Assets."""

        local_base_quantity = sum(
            position.quantity for position in local_portfolio.positions
        )

        return [
            self._compare_asset(local_base_quantity, balances, base_asset),
            self._compare_asset(local_portfolio.capital, balances, quote_asset),
        ]

    def _compare_asset(
        self,
        local_quantity: float,
        balances: list[BalanceSnapshot],
        asset: str,
    ) -> BalanceReconciliationResult:
        balance = next((b for b in balances if b.asset == asset), None)

        if balance is None:
            binance_quantity = 0.0
            reason = f"{asset!r} nicht im Binance-Kontostand gefunden"
        else:
            binance_quantity = balance.total
            reason = (
                "Übereinstimmung"
                if abs(local_quantity - binance_quantity) <= _MATCH_TOLERANCE
                else "Abweichung"
            )

        difference = local_quantity - binance_quantity
        matched = abs(difference) <= _MATCH_TOLERANCE

        return BalanceReconciliationResult(
            asset=asset,
            local_quantity=local_quantity,
            binance_quantity=binance_quantity,
            matched=matched,
            reason=reason,
            difference=difference,
        )
