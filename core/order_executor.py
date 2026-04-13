"""Reliable order execution with idempotency, retries, and fill verification."""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Literal


TerminalStatus = Literal[
    "new",
    "accepted",
    "pending_new",
    "partially_filled",
    "filled",
    "canceled",
    "rejected",
    "expired",
    "done_for_day",
]


@dataclass
class ExecutionResult:
    """Order execution outcome."""

    client_order_id: str
    broker_order_id: str
    status: str
    filled_qty: int
    avg_fill_price: float
    attempts: int
    latency_ms: int
    partial_fill: bool
    message: str


class OrderExecutionError(RuntimeError):
    """Base execution error."""


class OrderRejectedError(OrderExecutionError):
    """Order was rejected by the broker."""


class OrderUnfilledError(OrderExecutionError):
    """Order was not fully filled before timeout."""


class ReliableOrderExecutor:
    """Executes market orders with idempotent IDs and robust retries."""

    def __init__(
        self,
        api,
        logger: Optional[logging.Logger] = None,
        max_retries: int = 3,
        initial_backoff_sec: float = 1.0,
        verify_fill_timeout_sec: float = 30.0,
        poll_interval_sec: float = 1.0,
    ) -> None:
        self.api = api
        self.logger = logger or logging.getLogger("order-executor")
        self.max_retries = max(1, int(max_retries))
        self.initial_backoff_sec = max(0.0, float(initial_backoff_sec))
        self.verify_fill_timeout_sec = max(1.0, float(verify_fill_timeout_sec))
        self.poll_interval_sec = max(0.1, float(poll_interval_sec))

    @staticmethod
    def _build_client_order_id(symbol: str, side: str, qty: int) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        return f"tb_{ts}_{symbol}_{side}_{qty}"[:48]

    @staticmethod
    def _as_int(value, default: int = 0) -> int:
        try:
            return int(float(value))
        except Exception:
            return default

    @staticmethod
    def _as_float(value, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return default

    @staticmethod
    def _is_terminal(status: str) -> bool:
        return status in {"filled", "canceled", "rejected", "expired", "done_for_day"}

    def _fetch_by_client_id(self, client_order_id: str):
        getter = getattr(self.api, "get_order_by_client_order_id", None)
        if getter is None:
            return None
        try:
            return getter(client_order_id)
        except Exception:
            return None

    def _fetch_by_broker_id(self, broker_order_id: str):
        getter = getattr(self.api, "get_order", None)
        if getter is None:
            return None
        try:
            return getter(broker_order_id)
        except Exception:
            return None

    def _wait_for_terminal(self, client_order_id: str, broker_order_id: str):
        deadline = time.monotonic() + self.verify_fill_timeout_sec
        latest = None

        while time.monotonic() < deadline:
            order = self._fetch_by_client_id(client_order_id)
            if order is None and broker_order_id:
                order = self._fetch_by_broker_id(broker_order_id)

            if order is not None:
                latest = order
                status = str(getattr(order, "status", "")).lower()
                if self._is_terminal(status):
                    return latest
                if status == "partially_filled":
                    self.logger.warning(
                        "Order partially filled | client_order_id=%s | filled_qty=%s",
                        client_order_id,
                        getattr(order, "filled_qty", 0),
                    )
            time.sleep(self.poll_interval_sec)

        return latest

    def place_market_order(
        self,
        symbol: str,
        side: Literal["buy", "sell", "BUY", "SELL"],
        qty: int,
        time_in_force: str = "day",
        client_order_id: Optional[str] = None,
    ) -> ExecutionResult:
        """Place and verify a market order with retries/backoff."""
        qty = int(qty)
        if qty <= 0:
            raise ValueError("qty must be > 0")

        normalized_side = str(side).lower()
        if normalized_side not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")

        start = time.monotonic()
        order_client_id = client_order_id or self._build_client_order_id(symbol, normalized_side, qty)
        last_error = None

        existing = self._fetch_by_client_id(order_client_id)
        if existing is not None:
            status = str(getattr(existing, "status", "")).lower()
            if status == "filled":
                return ExecutionResult(
                    client_order_id=order_client_id,
                    broker_order_id=str(getattr(existing, "id", "")),
                    status=status,
                    filled_qty=self._as_int(getattr(existing, "filled_qty", qty), qty),
                    avg_fill_price=self._as_float(getattr(existing, "filled_avg_price", 0.0), 0.0),
                    attempts=0,
                    latency_ms=int((time.monotonic() - start) * 1000),
                    partial_fill=False,
                    message="Existing filled order reused",
                )

        for attempt in range(1, self.max_retries + 1):
            try:
                submitted = self.api.submit_order(
                    symbol=symbol,
                    qty=qty,
                    side=normalized_side,
                    type="market",
                    time_in_force=time_in_force,
                    client_order_id=order_client_id,
                )
                broker_order_id = str(getattr(submitted, "id", ""))
                final = self._wait_for_terminal(order_client_id, broker_order_id)

                if final is None:
                    raise OrderUnfilledError(
                        f"Order timed out without broker status | client_order_id={order_client_id}"
                    )

                status = str(getattr(final, "status", "")).lower()
                filled_qty = self._as_int(getattr(final, "filled_qty", 0), 0)
                avg_price = self._as_float(getattr(final, "filled_avg_price", 0.0), 0.0)

                if status == "filled":
                    return ExecutionResult(
                        client_order_id=order_client_id,
                        broker_order_id=str(getattr(final, "id", broker_order_id)),
                        status=status,
                        filled_qty=filled_qty,
                        avg_fill_price=avg_price,
                        attempts=attempt,
                        latency_ms=int((time.monotonic() - start) * 1000),
                        partial_fill=filled_qty < qty,
                        message="Order filled",
                    )

                if status == "rejected":
                    raise OrderRejectedError(
                        f"Order rejected | client_order_id={order_client_id} | attempt={attempt}"
                    )

                raise OrderUnfilledError(
                    f"Order not filled | status={status or 'unknown'} | client_order_id={order_client_id}"
                )

            except OrderRejectedError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                backoff = self.initial_backoff_sec * (2 ** (attempt - 1))
                self.logger.warning(
                    "Order attempt failed, retrying | symbol=%s side=%s qty=%s attempt=%s/%s backoff=%.1fs error=%s",
                    symbol,
                    normalized_side,
                    qty,
                    attempt,
                    self.max_retries,
                    backoff,
                    exc,
                )
                time.sleep(backoff)

        raise OrderExecutionError(
            f"Order execution failed after {self.max_retries} attempts | client_order_id={order_client_id} | error={last_error}"
        )
