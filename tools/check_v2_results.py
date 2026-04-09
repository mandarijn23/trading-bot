#!/usr/bin/env python3
"""Check the actual v2 JSON report."""

import paramiko
import json
import os
import tempfile
from pathlib import Path

host = os.getenv("NAS_HOST", "192.168.1.70")
user = os.getenv("NAS_USER", "nas")
password = os.getenv("NAS_SSH_PASSWORD", "")


def _normalize_fingerprint(value: str) -> str:
    return value.replace(":", "").strip().lower()


def _connect_ssh(password: str) -> paramiko.SSHClient:
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(
        host,
        username=user,
        password=password,
        timeout=30,
        banner_timeout=30,
        auth_timeout=30,
        look_for_keys=False,
        allow_agent=False,
    )

    expected_fp = os.getenv("NAS_HOST_FINGERPRINT", "").strip()
    if expected_fp:
        remote_key = ssh.get_transport().get_remote_server_key()
        actual_fp = remote_key.get_fingerprint().hex()
        if _normalize_fingerprint(actual_fp) != _normalize_fingerprint(expected_fp):
            ssh.close()
            raise RuntimeError(
                f"SSH host fingerprint mismatch for {host}. Expected {expected_fp}, got {actual_fp}."
            )

    return ssh

if not password:
    raise SystemExit("Set NAS_SSH_PASSWORD in environment before running.")

print("[*] Connecting to NAS...")
ssh = _connect_ssh(password)

print("[*] Fetching training_report.json...")
sftp = ssh.open_sftp()
tmp_dir = Path(tempfile.gettempdir())
local_report = tmp_dir / "training_report.json"
try:
    sftp.get("/home/nas/trading-bot/training_report.json", str(local_report))
except Exception as e:
    print(f"[!] Error: {e}")
    sftp.close()
    ssh.close()
    exit(1)

sftp.close()

with local_report.open(encoding="utf-8") as f:
    report = json.load(f)

ssh.close()

print("\n" + "="*80)
print("LATEST TRAINING REPORT (JSON):")
print("="*80)
print(f"Generated: {report.get('generated_at')}")
print(f"Symbols: {report.get('symbols')}")
print(f"Quality: {report.get('quality_band')} ({report.get('quality_label')})")
print(f"Accuracy: {report.get('overall_accuracy'):.3f}")
print(f"F1: {report.get('overall_f1'):.3f}")
print(f"AUC: {report.get('overall_auc'):.3f}")
print(f"Holdout n: {report.get('total_test_samples')}")
print(f"Cached samples reused: {report.get('cached_samples_reused', 'N/A')}")
print(f"Dedup dropped: {report.get('deduplicated_samples_dropped', 'N/A')}")
print(f"Total train samples: {report.get('total_train_samples', 'N/A')}")
overlap_ratio = report.get('train_test_overlap_ratio', 'N/A')
if isinstance(overlap_ratio, (int, float)):
    print(f"Train/test overlap: {overlap_ratio:.2%}")
else:
    print(f"Train/test overlap: {overlap_ratio}")
print(f"Threshold: {report.get('threshold_pct', 'N/A')}%")

if "bootstrap_metrics" in report and report["bootstrap_metrics"]:
    print(f"Bootstrap AUC: {report['bootstrap_metrics'].get('auc_mean', 0):.3f} "
          f"[{report['bootstrap_metrics'].get('auc_ci_low', 0):.3f}–"
          f"{report['bootstrap_metrics'].get('auc_ci_high', 0):.3f}]")

print("\n✓ v2 Features Detected:")
if report.get('cached_samples_reused') is not None:
    print("  ✓ Sample cache accumulation")
if report.get('deduplicated_samples_dropped') is not None:
    print("  ✓ Sample deduplication")
if report.get('train_test_overlap_ratio') is not None:
    print("  ✓ Leakage overlap check")
if report.get('threshold_pct'):
    print(f"  ✓ 0.5% label threshold")
if "bootstrap_metrics" in report:
    print("  ✓ Bootstrap confidence intervals")
