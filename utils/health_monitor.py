"""Runtime health checks for API heartbeat and host resource pressure."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from shutil import disk_usage
import os


@dataclass
class HealthIssue:
    """One health issue raised by a monitor check."""

    component: str
    level: str
    message: str
    value: float | None = None
    threshold: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class HealthMonitor:
    """Evaluate runtime health signals without extra third-party dependencies."""

    def __init__(
        self,
        cpu_load_warn_pct: float = 90.0,
        memory_warn_pct: float = 90.0,
        disk_warn_pct: float = 90.0,
        api_stale_sec: int = 180,
    ) -> None:
        self.cpu_load_warn_pct = float(cpu_load_warn_pct)
        self.memory_warn_pct = float(memory_warn_pct)
        self.disk_warn_pct = float(disk_warn_pct)
        self.api_stale_sec = max(5, int(api_stale_sec))

    @staticmethod
    def _now_utc() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _read_meminfo() -> tuple[float | None, float | None]:
        """Return total and available memory in kB from /proc/meminfo."""
        try:
            total_kb = None
            available_kb = None
            with open("/proc/meminfo", "r", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("MemTotal:"):
                        total_kb = float(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        available_kb = float(line.split()[1])
            return total_kb, available_kb
        except Exception:
            return None, None

    def system_metrics(self) -> dict[str, float | None]:
        """Collect host metrics used by health checks."""
        cpu_load_pct = None
        try:
            load_1m = float(os.getloadavg()[0])
            cpu_count = max(1, int(os.cpu_count() or 1))
            cpu_load_pct = (load_1m / cpu_count) * 100.0
        except Exception:
            cpu_load_pct = None

        mem_used_pct = None
        total_kb, available_kb = self._read_meminfo()
        if total_kb and available_kb is not None and total_kb > 0:
            mem_used_pct = ((total_kb - available_kb) / total_kb) * 100.0

        disk_used_pct = None
        try:
            total, used, _free = disk_usage("/")
            if total > 0:
                disk_used_pct = (float(used) / float(total)) * 100.0
        except Exception:
            disk_used_pct = None

        return {
            "cpu_load_pct": cpu_load_pct,
            "memory_used_pct": mem_used_pct,
            "disk_used_pct": disk_used_pct,
        }

    def evaluate(
        self,
        last_api_heartbeat_at: datetime | None,
        now: datetime | None = None,
        api_required: bool = True,
    ) -> dict:
        """Run all checks and return aggregate health status."""
        now_ts = now or self._now_utc()
        issues: list[HealthIssue] = []
        metrics = self.system_metrics()

        cpu_load_pct = metrics.get("cpu_load_pct")
        if cpu_load_pct is not None and cpu_load_pct >= self.cpu_load_warn_pct:
            issues.append(
                HealthIssue(
                    component="cpu",
                    level="warning",
                    message="CPU load is above threshold",
                    value=float(cpu_load_pct),
                    threshold=self.cpu_load_warn_pct,
                )
            )

        memory_used_pct = metrics.get("memory_used_pct")
        if memory_used_pct is not None and memory_used_pct >= self.memory_warn_pct:
            issues.append(
                HealthIssue(
                    component="memory",
                    level="warning",
                    message="Memory usage is above threshold",
                    value=float(memory_used_pct),
                    threshold=self.memory_warn_pct,
                )
            )

        disk_used_pct = metrics.get("disk_used_pct")
        if disk_used_pct is not None and disk_used_pct >= self.disk_warn_pct:
            issues.append(
                HealthIssue(
                    component="disk",
                    level="warning",
                    message="Disk usage is above threshold",
                    value=float(disk_used_pct),
                    threshold=self.disk_warn_pct,
                )
            )

        heartbeat_age_sec = None
        if last_api_heartbeat_at is not None:
            try:
                heartbeat_age_sec = max(0.0, (now_ts - last_api_heartbeat_at).total_seconds())
            except Exception:
                heartbeat_age_sec = None

        if api_required:
            if heartbeat_age_sec is None:
                issues.append(
                    HealthIssue(
                        component="api",
                        level="critical",
                        message="No API heartbeat recorded",
                        value=None,
                        threshold=float(self.api_stale_sec),
                    )
                )
            elif heartbeat_age_sec >= self.api_stale_sec:
                issues.append(
                    HealthIssue(
                        component="api",
                        level="critical",
                        message="API heartbeat is stale",
                        value=float(heartbeat_age_sec),
                        threshold=float(self.api_stale_sec),
                    )
                )

        return {
            "timestamp": now_ts.isoformat(),
            "metrics": metrics,
            "heartbeat_age_sec": heartbeat_age_sec,
            "issues": [issue.to_dict() for issue in issues],
            "has_warning": any(issue.level == "warning" for issue in issues),
            "has_critical": any(issue.level == "critical" for issue in issues),
        }