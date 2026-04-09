#!/usr/bin/env python3
"""Deploy performance system to NAS using sftp and git pull."""

import subprocess
import sys
import getpass
from pathlib import Path

NAS_HOST = "192.168.1.70"
NAS_USER = "root"
NAS_REPO = "/home/nas/trading-bot"

# Get password
password = getpass.getpass("Enter NAS root password: ")

# Use sshpass to run commands
commands = [
    # Verify connection and update from GitHub
    f'echo "{password}" | sshpass -p {password} ssh {NAS_USER}@{NAS_HOST} "cd {NAS_REPO} && git pull origin master"',
    
    # Normalize line endings in shell scripts
    f'echo "{password}" | sshpass -p {password} ssh {NAS_USER}@{NAS_HOST} "find {NAS_REPO}/tools -name \'*.sh\' -exec dos2unix {{}} \\;"',
    
    # Ensure executability
    f'echo "{password}" | sshpass -p {password} ssh {NAS_USER}@{NAS_HOST} "chmod +x {NAS_REPO}/tools/*.sh"',
    
    # Restart services
    f'echo "{password}" | sshpass -p {password} ssh {NAS_USER}@{NAS_HOST} "systemctl restart trading-bot-stock trading-bot-train-hourly"',
    
    # Show status
    f'echo "{password}" | sshpass -p {password} ssh {NAS_USER}@{NAS_HOST} "systemctl status trading-bot-train-hourly --no-pager | head -20"',
]

print("[*] Deploying to NAS...")
for i, cmd in enumerate(commands, 1):
    print(f"[*] Step {i}...")
    try:
        result = subprocess.run(cmd, shell=True, timeout=30, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[!] Command failed: {result.stderr[:200]}")
        else:
            print(f"[+] Success: {result.stdout[:100] if result.stdout else '(no output)'}")
    except subprocess.TimeoutExpired:
        print(f"[!] Command timeout")
    except Exception as e:
        print(f"[!] Error: {e}")

print("\n✅ Deployment complete!")
