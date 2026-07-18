"""Laufzeit-Konfiguration für den CLI-Einstiegspunkt.

Liest Standardwerte aus `config/settings.py`, überschreibbar durch explizite
Argumente. Reine Datenstruktur - keine Objekt-Konstruktion (siehe
`tradingbot.cli.composition`, dem einzigen Ort dafür).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from tradingbot.config.settings import DEFAULT_CAPITAL, MAX_RISK_PER_TRADE, RUNTIME_DATA_DIR

_DEFAULT_DB_PATH = str(RUNTIME_DATA_DIR / "trading.sqlite3")


class RuntimeMode(Enum):
    """Welcher Broker für eine Runtime-Session verwendet wird.

    Bewusst nur die drei Broker-Varianten, die sich denselben Objektgraphen
    (`PaperTradingEngine`, SQLite-Repositories, `SimpleLoopScheduler`)
    teilen - Backtest ist strukturell getrennt (eigener Einstiegspunkt,
    kein `PaperTradingEngine`, siehe `backtest/`) und hat deshalb bewusst
    keinen `RuntimeMode`-Wert.

    `LIVE` ist in `cli/composition.py` als Broker-Factory registriert und
    führt über den `LiveBroker` echte Binance-Spot-Market-Orders aus (siehe
    `execution/live_broker.py`) - ausschliesslich hinter dem vollständigen
    Sicherheits-Gate (exakte Bestätigungsphrase, vollständige Credentials,
    gültige `TRADINGBOT_LIVE_ENVIRONMENT`; siehe `_build_live_broker`).
    Fehlt eine dieser Voraussetzungen, schlägt der Aufbau bewusst mit einem
    klaren Fehler fehl, statt still auf einen anderen Broker
    zurückzufallen.
    """

    PAPER = "paper"
    MOCK = "mock"
    LIVE = "live"


@dataclass
class RuntimeConfig:
    """Vollständig aufgelöste Konfiguration für eine Paper-Trading-Session."""

    symbol: str
    timeframe: str
    candle_limit: int
    interval_seconds: float
    initial_capital: float
    fee_percent: float
    slippage_percent: float
    max_position_size: float
    max_daily_loss_percent: float
    max_drawdown_percent: float
    max_exposure_percent: float
    max_exposure_per_asset_percent: float
    strategy_name: str
    db_path: str
    mode: RuntimeMode = RuntimeMode.PAPER
    session_id: str | None = None


def build_config(
    *,
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
    candle_limit: int = 50,
    interval_seconds: float = 60.0,
    initial_capital: float | None = None,
    fee_percent: float = 0.0,
    slippage_percent: float = 0.0,
    max_position_size: float | None = None,
    max_daily_loss_percent: float = 5.0,
    max_drawdown_percent: float = 20.0,
    max_exposure_percent: float = 80.0,
    max_exposure_per_asset_percent: float = 30.0,
    strategy_name: str = "simple",
    db_path: str | None = None,
    mode: RuntimeMode = RuntimeMode.PAPER,
    session_id: str | None = None,
) -> RuntimeConfig:
    """Löst eine vollständige `RuntimeConfig` auf.

    Nicht explizit übergebene Werte fallen auf Defaults aus
    `config/settings.py` zurück: `initial_capital` auf `DEFAULT_CAPITAL`,
    `max_position_size` auf `DEFAULT_CAPITAL * MAX_RISK_PER_TRADE` (Annahme:
    `MAX_RISK_PER_TRADE` als Kapitalanteil je Position - jederzeit per
    `--max-position-size` explizit überschreibbar), `db_path` auf eine Datei
    unterhalb von `RUNTIME_DATA_DIR`.
    """

    return RuntimeConfig(
        symbol=symbol,
        timeframe=timeframe,
        candle_limit=candle_limit,
        interval_seconds=interval_seconds,
        initial_capital=initial_capital if initial_capital is not None else DEFAULT_CAPITAL,
        fee_percent=fee_percent,
        slippage_percent=slippage_percent,
        max_position_size=(
            max_position_size
            if max_position_size is not None
            else DEFAULT_CAPITAL * MAX_RISK_PER_TRADE
        ),
        max_daily_loss_percent=max_daily_loss_percent,
        max_drawdown_percent=max_drawdown_percent,
        max_exposure_percent=max_exposure_percent,
        max_exposure_per_asset_percent=max_exposure_per_asset_percent,
        strategy_name=strategy_name,
        db_path=db_path if db_path is not None else _DEFAULT_DB_PATH,
        mode=mode,
        session_id=session_id,
    )
