from tradingbot.paper_trading.scheduler import Scheduler, SimpleLoopScheduler


def test_simple_loop_scheduler_is_a_scheduler():

    assert isinstance(SimpleLoopScheduler(), Scheduler)


def test_run_calls_callback_repeatedly_until_stopped():

    calls: list[int] = []
    scheduler = SimpleLoopScheduler(sleep=lambda _seconds: None)

    def callback() -> None:
        calls.append(1)
        if len(calls) == 3:
            scheduler.stop()

    scheduler.run(callback, interval_seconds=0.0)

    assert len(calls) == 3


def test_run_does_not_sleep_after_final_callback():

    sleep_calls: list[float] = []
    scheduler = SimpleLoopScheduler(sleep=sleep_calls.append)

    def callback() -> None:
        scheduler.stop()

    scheduler.run(callback, interval_seconds=5.0)

    assert sleep_calls == []


def test_run_sleeps_with_given_interval_between_calls():

    sleep_calls: list[float] = []
    calls: list[int] = []
    scheduler = SimpleLoopScheduler(sleep=sleep_calls.append)

    def callback() -> None:
        calls.append(1)
        if len(calls) == 2:
            scheduler.stop()

    scheduler.run(callback, interval_seconds=2.5)

    assert sleep_calls == [2.5]
