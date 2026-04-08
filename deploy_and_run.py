#!/usr/bin/env python3
"""Deploy trainer and run hourly training with password auth."""

import paramiko
import time
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
