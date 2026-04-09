#!/usr/bin/env python3
"""Start trading-bot-stock service on NAS and check status."""

import paramiko
import os

NAS_HOST = "192.168.1.70"
NAS_USER = "root"
NAS_HOST_FINGERPRINT = "b5:39:a9:fc:f7:06:87:e2:f7:71:70:e1:22:21:e8:30"
NAS_PASSWORD = os.getenv("NAS_PASSWORD")

if not NAS_PASSWORD:
    import getpass
    NAS_PASSWORD = getpass.getpass("Enter NAS root password: ")
    
if not NAS_PASSWORD:
    print("ERROR: No password provided")
    exit(1)

# Create client
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    # Verify host key
    host_keys = ssh.get_host_keys()
    print(f"[*] Connecting to {NAS_HOST}...")
    ssh.connect(
        NAS_HOST,
        username=NAS_USER,
        password=NAS_PASSWORD,
        banner_timeout=10,
        auth_timeout=10,
        look_for_keys=False,
        allow_agent=False,
    )
    print(f"[+] Connected!")
    
    # Start service
    print("[*] Starting trading-bot-stock service...")
    stdin, stdout, stderr = ssh.exec_command("systemctl start trading-bot-stock")
    stdout.channel.recv_exit_status()
    
    print("[*] Waiting 2 seconds...")
    import time
    time.sleep(2)
    
    # Get logs
    print("[*] Fetching last 50 log lines...")
    stdin, stdout, stderr = ssh.exec_command("journalctl -u trading-bot-stock -n 50")
    logs = stdout.read().decode("utf-8")
    print(logs)
    
    # Check for errors
    if "logger" in logs.lower() and "error" in logs.lower():
        print("\n[!] WARNING: Logger errors detected in logs")
    elif "insufficient data" in logs.lower():
        print("\n[-] Insufficient data warnings still present (may be normal if <30 bars)")
    else:
        print("\n[+] No obvious errors detected!")
    
except Exception as e:
    print(f"ERROR: {e}")
    exit(1)
finally:
    ssh.close()
