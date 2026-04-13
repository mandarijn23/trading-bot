"""Tests for reliable order execution and stuck-order watchdog."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from order_executor import ReliableOrderExecutor, OrderExecutionError
from order_watchdog import OrderWatchdog


class _FakeAPI:
    def __init__(self):
        self.orders_by_client = {}
        self.submit_calls = 0
        self.fail_first_submit = False
        self.open_orders = []
        self.canceled = []

    def submit_order(self, **kwargs):
        self.submit_calls += 1
        if self.fail_first_submit and self.submit_calls == 1:
            raise RuntimeError("temporary broker error")

        client_order_id = kwargs["client_order_id"]
        order = SimpleNamespace(
            id=f"oid-{self.submit_calls}",
            client_order_id=client_order_id,
            status="new",
            filled_qty="0",
            filled_avg_price="0",
            symbol=kwargs.get("symbol", ""),
            side=kwargs.get("side", ""),
            created_at=datetime.now(timezone.utc),
        )
        self.orders_by_client[client_order_id] = order
        return order

    def get_order_by_client_order_id(self, client_order_id):
        order = self.orders_by_client.get(client_order_id)
        if order is None:
            raise RuntimeError("not found")

        if order.status == "new":
            order.status = "filled"
            order.filled_qty = "5"
            order.filled_avg_price = "101.25"
        return order

    def list_orders(self, status="open"):
        if status != "open":
            return []
        return list(self.open_orders)

    def cancel_order(self, order_id):
        self.canceled.append(order_id)


def test_executor_fills_order_with_verification():
    api = _FakeAPI()
    executor = ReliableOrderExecutor(
        api,
        max_retries=2,
        initial_backoff_sec=0.0,
        verify_fill_timeout_sec=2.0,
        poll_interval_sec=0.1,
    )

    result = executor.place_market_order("SPY", "buy", 5, client_order_id="fixed-1")

    assert result.status == "filled"
    assert result.filled_qty == 5
    assert result.avg_fill_price == 101.25
    assert api.submit_calls == 1


def test_executor_retries_after_transient_failure():
    api = _FakeAPI()
    api.fail_first_submit = True

    executor = ReliableOrderExecutor(
        api,
        max_retries=3,
        initial_backoff_sec=0.0,
        verify_fill_timeout_sec=2.0,
        poll_interval_sec=0.1,
    )

    result = executor.place_market_order("QQQ", "sell", 5, client_order_id="fixed-2")

    assert result.status == "filled"
    assert api.submit_calls == 2


def test_executor_raises_when_all_attempts_fail():
    class _AlwaysFailAPI(_FakeAPI):
        def submit_order(self, **kwargs):
            raise RuntimeError("broker unavailable")

    api = _AlwaysFailAPI()
    executor = ReliableOrderExecutor(api, max_retries=2, initial_backoff_sec=0.0)

    raised = False
    try:
        executor.place_market_order("VOO", "buy", 3, client_order_id="fixed-3")
    except OrderExecutionError:
        raised = True

    assert raised is True


def test_watchdog_detects_and_cancels_stuck_orders():
    api = _FakeAPI()
    stale = SimpleNamespace(
        id="oid-stale",
        client_order_id="cid-stale",
        symbol="SPY",
        side="buy",
        status="new",
        created_at=datetime.now(timezone.utc) - timedelta(seconds=45),
    )
    fresh = SimpleNamespace(
        id="oid-fresh",
        client_order_id="cid-fresh",
        symbol="QQQ",
        side="buy",
        status="new",
        created_at=datetime.now(timezone.utc) - timedelta(seconds=5),
    )
    api.open_orders = [stale, fresh]

    watchdog = OrderWatchdog(api, max_open_seconds=30, auto_cancel=True)
    alerts = watchdog.check_once()

    assert len(alerts) == 1
    assert alerts[0].order_id == "oid-stale"
    assert api.canceled == ["oid-stale"]
