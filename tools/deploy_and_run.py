#!/usr/bin/env python3
"""Deploy trainer and run hourly training with password auth."""

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
	parser = argparse.ArgumentParser(description="Deploy trainer and run hourly training")
	parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
	parser.add_argument("--dry-run", action="store_true", help="Print planned actions and exit")
	args = parser.parse_args()

	if args.dry_run:
		print(f"[DRY RUN] Would connect to {user}@{host}")
		print("[DRY RUN] Would upload train_stock_rf.py to /home/nas/trading-bot/train_stock_rf.py")
		print("[DRY RUN] Would start trading-bot-train-hourly.service")
		print("[DRY RUN] Would tail /home/nas/trading-bot/hourly_train.log")
		return

	if not args.yes:
		answer = input(f"Deploy to {user}@{host} and start training service? [y/N]: ").strip().lower()
		if answer not in {"y", "yes"}:
			print("Aborted")
			return

	password = os.getenv("NAS_SSH_PASSWORD", "")
	if not password:
		raise SystemExit("Set NAS_SSH_PASSWORD in environment before running.")

	print("[*] Connecting to NAS...")
	ssh = _connect_ssh(password)

	print("[*] Uploading train_stock_rf.py...")
	sftp = ssh.open_sftp()
	sftp.put("train_stock_rf.py", "/home/nas/trading-bot/train_stock_rf.py")
	sftp.close()
	print("[✓] File uploaded")

	print("[*] Starting hourly training service...")
	stdin, stdout, stderr = ssh.exec_command("sudo systemctl start trading-bot-train-hourly.service")
	stdout.read()
	time.sleep(7)

	print("[*] Fetching log output...")
	stdin, stdout, stderr = ssh.exec_command("tail -n 100 /home/nas/trading-bot/hourly_train.log")
	log_output = stdout.read().decode("utf-8", errors="ignore")

	ssh.close()

	print("\n" + "="*80)
	print("TRAINING RUN OUTPUT:")
	print("="*80)
	print(log_output)


if __name__ == "__main__":
	main()
