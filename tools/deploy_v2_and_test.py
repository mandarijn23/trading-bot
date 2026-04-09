#!/usr/bin/env python3
"""Deploy and test v2 trainer on NAS."""

import argparse
import paramiko
import time
import os

host = os.getenv("NAS_HOST", "192.168.1.70")
user = os.getenv("NAS_USER", "nas")


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy and test v2 trainer on NAS")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions and exit")
    args = parser.parse_args()

    if args.dry_run:
        print(f"[DRY RUN] Would connect to {user}@{host}")
        print("[DRY RUN] Would upload models/train_stock_rf_v2.py and resend_training_report.py")
        print("[DRY RUN] Would upload tools/hourly_train_and_report.sh and start service")
        print("[DRY RUN] Would tail /home/nas/trading-bot/hourly_train.log")
        return

    if not args.yes:
        answer = input(f"Deploy v2 trainer to {user}@{host} and start service? [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Aborted")
            return

    password = os.getenv("NAS_SSH_PASSWORD", "")
    if not password:
        raise SystemExit("Set NAS_SSH_PASSWORD in environment before running.")

    print("[*] Connecting to NAS...")
    ssh = _connect_ssh(password)

    print("[*] Uploading v2 trainer...")
    sftp = ssh.open_sftp()
    sftp.put("models/train_stock_rf_v2.py", "/home/nas/trading-bot/models/train_stock_rf_v2.py")
    sftp.put("resend_training_report.py", "/home/nas/trading-bot/resend_training_report.py")
    sftp.put("tools/hourly_train_and_report.sh", "/home/nas/trading-bot/tools/hourly_train_and_report.sh")
    sftp.close()

    # Normalize line endings for uploaded scripts on Linux hosts.
    ssh.exec_command(
        "perl -pi -e 's/\\r$//' "
        "/home/nas/trading-bot/tools/hourly_train_and_report.sh "
        "/home/nas/trading-bot/resend_training_report.py"
    )
    print("[✓] v2 uploaded")

    print("[*] Verifying hourly script path...")
    stdin, stdout, stderr = ssh.exec_command("tail -n 30 /home/nas/trading-bot/tools/hourly_train_and_report.sh")
    script_content = stdout.read().decode("utf-8", errors="ignore")
    print("[✓] Script ready:\n" + script_content)

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


if __name__ == "__main__":
    main()
