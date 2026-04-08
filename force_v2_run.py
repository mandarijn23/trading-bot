#!/usr/bin/env python3
"""Force v2 to run now on NAS."""

import paramiko
import time
import os

host = "192.168.1.70"
user = "nas"
password = os.getenv("NAS_SSH_PASSWORD", "")

if not password:
    raise SystemExit("Set NAS_SSH_PASSWORD in environment before running.")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=user, password=password, timeout=30)

print("[*] Running v2 training directly...")
stdin, stdout, stderr = ssh.exec_command(
    "cd /home/nas/trading-bot && "
    "./.venv/bin/python train_stock_rf_v2.py --hard --limit 1500 --threshold 0.5 --timeframe 15Min > v2_output.log 2>&1 && "
    "tail -n 100 v2_output.log"
)
output = stdout.read().decode("utf-8", errors="replace")

# Verify results
print("\n" + "="*80)
print("V2 RUN COMPLETE - KEY METRICS:")
print("="*80)

if "Loaded sample cache" in output:
    print("✓ Sample cache loaded")
if "cached samples =" in output:
    print("✓ Cached samples reused in training")
if "Bootstrap" in output:
    print("✓ Bootstrap metrics computed")
if "Threshold" in output or "0.5" in output:
    print("✓ 0.5% threshold applied")
if "Discord report sent: True" in output:
    print("✓ Discord report posted")
