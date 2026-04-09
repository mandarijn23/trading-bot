#!/usr/bin/env python3
"""Force v2 to run now on NAS."""

import argparse
import paramiko
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
    parser = argparse.ArgumentParser(description="Force v2 training run on NAS")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--dry-run", action="store_true", help="Print planned command and exit")
    args = parser.parse_args()

    if args.dry_run:
        print(f"[DRY RUN] Would connect to {user}@{host}")
        print("[DRY RUN] Would run train_stock_rf_v2.py with --hard --limit 1500 --threshold 0.5 --timeframe 15Min")
        return

    if not args.yes:
        answer = input(f"Run forced v2 training on {user}@{host}? [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Aborted")
            return

    password = os.getenv("NAS_SSH_PASSWORD", "")
    if not password:
        raise SystemExit("Set NAS_SSH_PASSWORD in environment before running.")

    ssh = _connect_ssh(password)

    print("[*] Running v2 training directly...")
    stdin, stdout, stderr = ssh.exec_command(
        "cd /home/nas/trading-bot && "
        "./.venv/bin/python train_stock_rf_v2.py --hard --limit 1500 --threshold 0.5 --timeframe 15Min > v2_output.log 2>&1 && "
        "tail -n 100 v2_output.log"
    )
    output = stdout.read().decode("utf-8", errors="replace")
    ssh.close()

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


if __name__ == "__main__":
    main()
