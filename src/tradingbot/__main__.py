"""CLI-Einstiegspunkt: `python -m tradingbot <kommando> [optionen]`.

Reine argparse-Verdrahtung: parst Argumente, ruft `cli.composition` zum
Bauen/Laden der Objekte und `cli.commands` zur Ausführung/Formatierung auf.
Enthält selbst weder Objekt-Konstruktion noch Geschäftslogik.
"""

from __future__ import annotations

import argparse
import sys

from tradingbot.cli import commands, composition
from tradingbot.cli.config import build_config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tradingbot", description="Paper-Trading-Bot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start", help="Startet eine neue Paper-Trading-Session")
    start_parser.add_argument("--symbol", default="BTCUSDT")
    start_parser.add_argument("--timeframe", default="1h")
    start_parser.add_argument("--candle-limit", type=int, default=50)
    start_parser.add_argument("--interval-seconds", type=float, default=60.0)
    start_parser.add_argument("--initial-capital", type=float, default=None)
    start_parser.add_argument("--fee-percent", type=float, default=0.0)
    start_parser.add_argument("--slippage-percent", type=float, default=0.0)
    start_parser.add_argument("--max-position-size", type=float, default=None)
    start_parser.add_argument("--max-daily-loss-percent", type=float, default=5.0)
    start_parser.add_argument("--max-drawdown-percent", type=float, default=20.0)
    start_parser.add_argument("--max-exposure-percent", type=float, default=80.0)
    start_parser.add_argument("--max-exposure-per-asset-percent", type=float, default=30.0)
    start_parser.add_argument("--strategy", dest="strategy_name", default="simple")
    start_parser.add_argument("--db-path", default=None)
    start_parser.add_argument("--session-id", default=None)

    status_parser = subparsers.add_parser("status", help="Zeigt den Status einer Session")
    status_parser.add_argument("session_id")
    status_parser.add_argument("--db-path", default=None)

    health_parser = subparsers.add_parser(
        "health", help="Zeigt einen Health-Snapshot einer Session"
    )
    health_parser.add_argument("session_id")
    health_parser.add_argument("--db-path", default=None)

    sessions_parser = subparsers.add_parser("sessions", help="Listet alle bekannten Sessions")
    sessions_parser.add_argument("--db-path", default=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "start":
        config = build_config(
            symbol=args.symbol,
            timeframe=args.timeframe,
            candle_limit=args.candle_limit,
            interval_seconds=args.interval_seconds,
            initial_capital=args.initial_capital,
            fee_percent=args.fee_percent,
            slippage_percent=args.slippage_percent,
            max_position_size=args.max_position_size,
            max_daily_loss_percent=args.max_daily_loss_percent,
            max_drawdown_percent=args.max_drawdown_percent,
            max_exposure_percent=args.max_exposure_percent,
            max_exposure_per_asset_percent=args.max_exposure_per_asset_percent,
            strategy_name=args.strategy_name,
            db_path=args.db_path,
            session_id=args.session_id,
        )
        try:
            engine, scheduler = composition.build_engine(config)
        except ValueError as error:
            parser.error(str(error))
            return 2

        print(
            f"Session gestartet: {engine.session.session_id} "
            f"({config.symbol} {config.timeframe})"
        )
        exit_code = commands.run_start(engine, scheduler, config.interval_seconds)
        print(f"Session beendet: {engine.session.session_id}")
        return exit_code

    if args.command == "status":
        config = build_config(db_path=args.db_path)
        session = composition.load_session(config, args.session_id)
        text, exit_code = commands.format_status(session, args.session_id)
        print(text)
        return exit_code

    if args.command == "health":
        config = build_config(db_path=args.db_path)
        snapshot = composition.load_health_snapshot(config, args.session_id)
        text, exit_code = commands.format_health(snapshot, args.session_id)
        print(text)
        return exit_code

    if args.command == "sessions":
        config = build_config(db_path=args.db_path)
        all_sessions = composition.load_all_sessions(config)
        text, exit_code = commands.format_sessions(all_sessions)
        print(text)
        return exit_code

    parser.error(f"Unbekanntes Kommando: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
