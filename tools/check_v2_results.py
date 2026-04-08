#!/usr/bin/env python3
"""Check the actual v2 JSON report."""

import paramiko
import json
import os

host = "192.168.1.70"
user = "nas"
password = os.getenv("NAS_SSH_PASSWORD", "")

if not password:
    raise SystemExit("Set NAS_SSH_PASSWORD in environment before running.")

print("[*] Connecting to NAS...")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=user, password=password, timeout=30)

print("[*] Fetching training_report.json...")
sftp = ssh.open_sftp()
try:
    sftp.get("/home/nas/trading-bot/training_report.json", "/tmp/report.json")
except Exception as e:
    print(f"[!] Error: {e}")
    sftp.close()
    ssh.close()
    exit(1)

sftp.close()

with open("/tmp/report.json") as f:
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
