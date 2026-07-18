"""ExperimentLog: minimale In-Memory-Sammlung dokumentierter Experimente,
plus JSON-Export ohne Equity-Kurven/Candle-Daten.

Noch keine Datenbank-Abstraktion - bewusst klein gehalten.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from tradingbot.backtest.research_report import ResearchReport, ResearchSourceType
from tradingbot.research_tracking.models import (
    DatasetDescriptor,
    Experiment,
    ExperimentConfiguration,
    ExperimentMetadata,
    ExperimentRecord,
)
from tradingbot.research_tracking.versioning import current_git_commit


def _json_default(value: Any) -> Any:
    """Behandelt Typen, die `json.dump` nicht nativ serialisieren kann."""

    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"Objekt vom Typ {type(value)} ist nicht JSON-serialisierbar")


def to_record(experiment: Experiment) -> ExperimentRecord:
    """Projiziert ein `Experiment` auf eine export-taugliche
    `ExperimentRecord` - ohne Equity-Kurve, ohne Candle-Daten.
    """

    report = experiment.report
    metadata = experiment.metadata

    return ExperimentRecord(
        experiment_id=metadata.experiment_id,
        name=metadata.name,
        created_at=metadata.created_at,
        dataset=metadata.dataset,
        configuration=metadata.configuration,
        code_version=metadata.code_version,
        report_name=report.name,
        source_type=report.source_type.value,
        profit_loss=report.profit_loss,
        performance_percent=report.performance_percent,
        annualized_return_percent=report.annualized_return_percent,
        sharpe_ratio=report.sharpe_ratio,
        volatility_percent=report.volatility_percent,
        max_drawdown_percent=report.max_drawdown_percent,
        calmar_ratio=report.calmar_ratio,
        details=asdict(report.details),
    )


class ExperimentLog:
    """Minimale In-Memory-Sammlung dokumentierter Experimente."""

    def __init__(self) -> None:
        self._experiments: list[Experiment] = []

    def record(self, experiment: Experiment) -> None:
        """Fügt ein bereits erzeugtes Experiment hinzu."""

        self._experiments.append(experiment)

    def all(self) -> list[Experiment]:
        """Gibt alle aufgezeichneten Experimente zurück (Kopie der Liste)."""

        return list(self._experiments)

    def filter_by_source_type(self, source_type: ResearchSourceType) -> list[Experiment]:
        """Gibt alle Experimente zurück, deren Report vom angegebenen
        Quelltyp stammt."""

        return [
            experiment
            for experiment in self._experiments
            if experiment.report.source_type == source_type
        ]

    def latest(self) -> Experiment | None:
        """Gibt das zuletzt aufgezeichnete Experiment zurück, `None` bei
        leerem Log."""

        return self._experiments[-1] if self._experiments else None

    def to_records(self) -> list[ExperimentRecord]:
        """Projiziert alle Experimente auf export-taugliche
        `ExperimentRecord`-Objekte."""

        return [to_record(experiment) for experiment in self._experiments]

    def export_json(self, path: str) -> None:
        """Exportiert alle Experimente als JSON-Liste kompakter
        `ExperimentRecord`-Objekte - bewusst ohne Equity-Kurven/Candle-Daten.
        """

        records = [asdict(record) for record in self.to_records()]
        with open(path, "w", encoding="utf-8") as file:
            json.dump(records, file, default=_json_default, indent=2, ensure_ascii=False)


def record_experiment(
    log: ExperimentLog,
    report: ResearchReport,
    dataset: DatasetDescriptor,
    configuration: ExperimentConfiguration,
    name: str | None = None,
) -> Experiment:
    """Erstellt ein neues, vollständig dokumentiertes `Experiment`
    (automatische `experiment_id` per UUID4, aktueller Zeitstempel,
    optionaler Git-Commit) und speichert es im `ExperimentLog`.
    """

    metadata = ExperimentMetadata(
        experiment_id=str(uuid4()),
        name=name,
        created_at=datetime.now(UTC),
        dataset=dataset,
        configuration=configuration,
        code_version=current_git_commit(),
    )
    experiment = Experiment(metadata=metadata, report=report)
    log.record(experiment)
    return experiment
