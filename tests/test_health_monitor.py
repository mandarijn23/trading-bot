"""Tests for runtime health monitor checks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from health_monitor import HealthMonitor


def test_health_monitor_warns_on_resource_pressure(monkeypatch):
    monitor = HealthMonitor(cpu_load_warn_pct=80.0, memory_warn_pct=80.0, disk_warn_pct=80.0, api_stale_sec=180)

    monkeypatch.setattr(monitor, "system_metrics", lambda: {
        "cpu_load_pct": 92.0,
        "memory_used_pct": 85.0,
        "disk_used_pct": 88.0,
    })

    now = datetime(2026, 4, 13, 12, 0, tzinfo=timezone.utc)
    report = monitor.evaluate(last_api_heartbeat_at=now - timedelta(seconds=30), now=now)

    assert report["has_warning"] is True
    assert report["has_critical"] is False
    assert len(report["issues"]) == 3


def test_health_monitor_marks_stale_api_as_critical(monkeypatch):
    monitor = HealthMonitor(api_stale_sec=120)
    monkeypatch.setattr(monitor, "system_metrics", lambda: {
        "cpu_load_pct": 30.0,
        "memory_used_pct": 40.0,
        "disk_used_pct": 50.0,
    })

    now = datetime(2026, 4, 13, 12, 0, tzinfo=timezone.utc)
    report = monitor.evaluate(last_api_heartbeat_at=now - timedelta(seconds=400), now=now)

    assert report["has_critical"] is True
    assert any(issue["component"] == "api" for issue in report["issues"])


def test_health_monitor_handles_missing_api_heartbeat():
    monitor = HealthMonitor(api_stale_sec=60)
    report = monitor.evaluate(last_api_heartbeat_at=None, now=datetime(2026, 4, 13, tzinfo=timezone.utc), api_required=True)

    assert report["has_critical"] is True
    assert any(issue["message"] == "No API heartbeat recorded" for issue in report["issues"])