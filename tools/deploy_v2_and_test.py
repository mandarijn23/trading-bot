#!/usr/bin/env python3
"""Deploy and test v2 trainer on NAS."""

import time
import os

try:
    import paramiko
except ImportError:  # pragma: no cover - optional runtime dependency
    paramiko = None


def main() -> int:
    host = "192.168.1.70"
    user = "nas"
    password = os.getenv("NAS_SSH_PASSWORD", "")

    if paramiko is None:
        raise SystemExit("Install paramiko to run this deploy helper: pip install paramiko")
    if not password:
        raise SystemExit("Set NAS_SSH_PASSWORD in environment before running.")

    print("[*] Connecting to NAS...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=user, password=password, timeout=30)

    print("[*] Uploading v2 trainer...")
    sftp = ssh.open_sftp()
    sftp.put("train_stock_rf_v2.py", "/home/nas/trading-bot/train_stock_rf_v2.py")
    sftp.close()
    print("[✓] v2 uploaded")

    # Update hourly script to use v2
    print("[*] Updating hourly script to use v2...")
    stdin, stdout, stderr = ssh.exec_command(
        "sed -i 's/train_stock_rf.py/train_stock_rf_v2.py/g' /home/nas/trading-bot/hourly_train_and_report.sh && "
        "cat /home/nas/trading-bot/hourly_train_and_report.sh"
    )
    script_content = stdout.read().decode("utf-8", errors="ignore")
    print("[✓] Script updated:\n" + script_content[-300:])

    print("[*] Starting training service (v2)...")
    stdin, stdout, stderr = ssh.exec_command("sudo systemctl start trading-bot-train-hourly.service")
    stdout.read()
    time.sleep(8)

    print("[*] Fetching log output...")
    stdin, stdout, stderr = ssh.exec_command("tail -n 120 /home/nas/trading-bot/hourly_train.log")
    log_output = stdout.read().decode("utf-8", errors="ignore")

    ssh.close()

    print("\n" + "="*80)
    print("V2 TRAINING RUN OUTPUT:")
    print("="*80)
    print(log_output)
    print("\n" + "="*80)
    print("ANALYSIS:")
    print("="*80)

    if "Cached reused=" in log_output or "cached_samples_reused" in log_output:
        print("✓ Sample cache is working")
    if "Bootstrap" in log_output or "bootstrap_metrics" in log_output:
        print("✓ Bootstrap CI is computed")
    if "0.5%" in log_output or "threshold_pct" in log_output:
        print("✓ 0.5% threshold applied")
    if "Total train" in log_output:
        print("✓ Total training samples reported (should be higher than before)")

    print("\nNext step: Let v2 run for a few hours to accumulate samples cache,")
    print("then compare final model quality vs v1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
