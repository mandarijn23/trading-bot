"""Order watchdog for detecting stale open orders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Callable
import logging


@dataclass
class StuckOrderAlert:
    """Represents an open order that exceeded age threshold."""

    order_id: str
    client_order_id: str
    symbol: str
    side: str
    status: str
    age_seconds: float


class OrderWatchdog:
    """Scans broker open orders and flags stale orders."""

    def __init__(
        self,
        api,
        logger: Optional[logging.Logger] = None,
        max_open_seconds: int = 30,
        auto_cancel: bool = True,
        on_alert: Optional[Callable[[StuckOrderAlert], None]] = None,
    ) -> None:
        self.api = api
        self.logger = logger or logging.getLogger("order-watchdog")
        self.max_open_seconds = max(5, int(max_open_seconds))
        self.auto_cancel = bool(auto_cancel)
        self.on_alert = on_alert

    @staticmethod
    def _to_datetime(value) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        try:
            text = str(value).replace("Z", "+00:00")
            return datetime.fromisoformat(text)
        except Exception:
            return None

    def _list_open_orders(self):
        lister = getattr(self.api, "list_orders", None)
        if lister is None:
            return []
        try:
            return lister(status="open") or []
        except Exception as exc:
            self.logger.debug("Order watchdog list_orders failed: %s", exc)
            return []

    def _cancel_order(self, order_id: str) -> None:
        cancel = getattr(self.api, "cancel_order", None)
        if cancel is None:
            return
        try:
            cancel(order_id)
            self.logger.warning("Canceled stale order | order_id=%s", order_id)
        except Exception as exc:
            self.logger.warning("Failed to cancel stale order | order_id=%s error=%s", order_id, exc)

    def check_once(self) -> list[StuckOrderAlert]:
        """Check for open orders older than threshold and optionally cancel them."""
        now = datetime.now(timezone.utc)
        alerts: list[StuckOrderAlert] = []

        for order in self._list_open_orders():
            created_at = self._to_datetime(getattr(order, "created_at", None))
            if created_at is None:
                continue

            age_seconds = (now - created_at).total_seconds()
            if age_seconds < self.max_open_seconds:
                continue

            alert = StuckOrderAlert(
                order_id=str(getattr(order, "id", "")),
                client_order_id=str(getattr(order, "client_order_id", "")),
                symbol=str(getattr(order, "symbol", "")),
                side=str(getattr(order, "side", "")),
                status=str(getattr(order, "status", "")),
                age_seconds=age_seconds,
            )
            alerts.append(alert)

            self.logger.warning(
                "Stuck order detected | symbol=%s side=%s status=%s age=%.1fs order_id=%s client_order_id=%s",
                alert.symbol,
                alert.side,
                alert.status,
                alert.age_seconds,
                alert.order_id,
                alert.client_order_id,
            )

            if self.on_alert is not None:
                try:
                    self.on_alert(alert)
                except Exception as exc:
                    self.logger.debug("Watchdog alert callback failed: %s", exc)

            if self.auto_cancel and alert.order_id:
                self._cancel_order(alert.order_id)

        return alerts
