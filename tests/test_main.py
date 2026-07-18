import pytest

import tradingbot.__main__ as main_module


def _db_path(tmp_path) -> str:

    return str(tmp_path / "trading.sqlite3")


def test_main_requires_a_command():

    with pytest.raises(SystemExit):
        main_module.main([])


def test_main_status_unknown_session_returns_exit_code_1(tmp_path, capsys):

    exit_code = main_module.main(["status", "unknown-id", "--db-path", _db_path(tmp_path)])

    assert exit_code == 1
    assert "unknown-id" in capsys.readouterr().out


def test_main_health_unknown_session_returns_exit_code_1(tmp_path, capsys):

    exit_code = main_module.main(["health", "unknown-id", "--db-path", _db_path(tmp_path)])

    assert exit_code == 1
    assert "unknown-id" in capsys.readouterr().out


def test_main_sessions_empty_returns_exit_code_0(tmp_path, capsys):

    exit_code = main_module.main(["sessions", "--db-path", _db_path(tmp_path)])

    assert exit_code == 0
    assert "Keine Sessions" in capsys.readouterr().out


def test_main_start_invalid_strategy_returns_exit_code_2(tmp_path):

    with pytest.raises(SystemExit) as excinfo:
        main_module.main(
            [
                "start",
                "--strategy",
                "does-not-exist",
                "--db-path",
                _db_path(tmp_path),
            ]
        )

    assert excinfo.value.code == 2


def test_main_start_dispatches_to_run_start_with_parsed_config(tmp_path, monkeypatch, capsys):

    calls = {}

    class _FakeSession:
        session_id = "fake-session"

    class _FakeEngine:
        session = _FakeSession()

    class _FakeScheduler:
        pass

    def _fake_build_engine(config):
        calls["config"] = config
        return _FakeEngine(), _FakeScheduler()

    def _fake_run_start(engine, scheduler, interval_seconds):
        calls["engine"] = engine
        calls["scheduler"] = scheduler
        calls["interval_seconds"] = interval_seconds
        return 0

    monkeypatch.setattr(main_module.composition, "build_engine", _fake_build_engine)
    monkeypatch.setattr(main_module.commands, "run_start", _fake_run_start)

    exit_code = main_module.main(
        [
            "start",
            "--symbol",
            "ETHUSDT",
            "--interval-seconds",
            "5",
            "--db-path",
            _db_path(tmp_path),
        ]
    )

    assert exit_code == 0
    assert calls["config"].symbol == "ETHUSDT"
    assert calls["interval_seconds"] == 5.0
    assert isinstance(calls["engine"], _FakeEngine)

    out = capsys.readouterr().out
    assert "fake-session" in out
