"""Zentrale Einstellungen des Trading-Bots."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Betriebsmodus
MODE = "paper_trading"

# Datenpfade
DATA_DIR = BASE_DIR / "data"
HISTORICAL_DATA_DIR = DATA_DIR / "historisch"
RUNTIME_DATA_DIR = DATA_DIR / "laufzeit"

# Logs
LOG_DIR = BASE_DIR / "logs"

# Trading-Einstellungen
DEFAULT_CAPITAL = 10000.0

# Risiko
MAX_RISK_PER_TRADE = 0.02
