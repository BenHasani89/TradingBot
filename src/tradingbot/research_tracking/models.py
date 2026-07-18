"""Datenmodelle für die Research-Tracking-Schicht.

Dokumentiert reproduzierbare Research-Läufe - keine Trading-Logik.
`Experiment` referenziert einen bereits erzeugten `ResearchReport`
unverändert (keine Kopie, keine parallele Ergebnisstruktur) -
`ResearchReport` bleibt Single Source of Truth für die eigentlichen
Ergebnisdaten (inkl. Equity-Kurve).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from tradingbot.backtest.research_report import ResearchReport
from tradingbot.data.models import MarketCandle


@dataclass(frozen=True)
class DatasetDescriptor:
    """Beschreibt die für ein Experiment verwendeten Marktdaten, ohne die
    Kerzen selbst zu speichern - nur Reproduzierbarkeits-Metadaten."""

    symbols: tuple[str, ...]
    timeframe: str
    candle_count: dict[str, int]
    start_timestamp: datetime | None
    end_timestamp: datetime | None
    source: str


def describe_dataset(
    candles_by_symbol: dict[str, list[MarketCandle]],
    timeframe: str,
    source: str,
) -> DatasetDescriptor:
    """Erzeugt einen `DatasetDescriptor` aus bereits vorhandenen Kerzen.

    `timeframe` und `source` werden bewusst nicht aus den Kerzen abgeleitet
    (nicht zuverlässig rekonstruierbar), sondern explizit übergeben -
    dieselbe Linie wie `periods_per_year` in `metrics.py`.
    """

    symbols = tuple(candles_by_symbol.keys())
    candle_count = {symbol: len(candles) for symbol, candles in candles_by_symbol.items()}

    all_candles = [candle for candles in candles_by_symbol.values() for candle in candles]
    start_timestamp = min((c.timestamp for c in all_candles), default=None)
    end_timestamp = max((c.timestamp for c in all_candles), default=None)

    return DatasetDescriptor(
        symbols=symbols,
        timeframe=timeframe,
        candle_count=candle_count,
        start_timestamp=start_timestamp,
        end_timestamp=end_timestamp,
        source=source,
    )


@dataclass(frozen=True)
class ExperimentConfiguration:
    """Beschreibt, WIE ein Ergebnis erzeugt wurde - unabhängig davon,
    welcher Runner es ausgeführt hat."""

    component_type: str
    component_name: str
    parameters: dict[str, Any]
    runner_type: str


@dataclass(frozen=True)
class ExperimentMetadata:
    """Reproduzierbarkeits-Metadaten eines Experiments."""

    experiment_id: str
    name: str | None
    created_at: datetime
    dataset: DatasetDescriptor
    configuration: ExperimentConfiguration
    code_version: str | None


@dataclass(frozen=True)
class Experiment:
    """Ein dokumentierter Research-Lauf.

    Referenziert den bereits erzeugten `ResearchReport` unverändert - keine
    zweite, parallele Ergebnisstruktur.
    """

    metadata: ExperimentMetadata
    report: ResearchReport


@dataclass(frozen=True)
class ExperimentRecord:
    """Export-taugliche, kompakte Zusammenfassung eines Experiments.

    Enthält nur Metadaten und die skalaren Kennzahlen aus `ResearchReport` -
    bewusst **ohne** `equity_curve` (kann bei langen Backtests gross werden)
    und ohne Candle-Daten. Für vollständige Artefakte (inkl. Equity-Kurve)
    ist eine spätere, eigene `ArtifactStorage`-Schicht vorgesehen - nicht
    Teil dieser Phase.
    """

    experiment_id: str
    name: str | None
    created_at: datetime
    dataset: DatasetDescriptor
    configuration: ExperimentConfiguration
    code_version: str | None
    report_name: str
    source_type: str
    profit_loss: float
    performance_percent: float
    annualized_return_percent: float
    sharpe_ratio: float
    volatility_percent: float
    max_drawdown_percent: float
    calmar_ratio: float
    details: dict[str, Any]
