#!/usr/bin/env python3
"""Deploy updated scripts to NAS."""

import os
import sys
import paramiko
from pathlib import Path

NAS_HOST = "192.168.1.70"
NAS_USER = "root"

# Get password from environment or prompt
import getpass
NAS_PASSWORD = os.getenv("NAS_PASSWORD")
if not NAS_PASSWORD:
    NAS_PASSWORD = getpass.getpass("Enter NAS root password: ")

NAS_REPO = "/home/nas/trading-bot"

FILES_TO_DEPLOY = [
    ("tools/hourly_performance_report.py", f"{NAS_REPO}/tools/hourly_performance_report.py"),
    ("tools/hourly_train_and_report.sh", f"{NAS_REPO}/tools/hourly_train_and_report.sh"),
    ("tools/hourly_report_and_train.sh", f"{NAS_REPO}/tools/hourly_report_and_train.sh"),
    ("core/stock_bot.py", f"{NAS_REPO}/core/stock_bot.py"),
    ("config/stock_config.py", f"{NAS_REPO}/config/stock_config.py"),
    ("tests/test_hourly_performance_report.py", f"{NAS_REPO}/tests/test_hourly_performance_report.py"),
]

def normalize_line_endings(content: bytes, to_lf: bool = True) -> bytes:
    """Normalize line endings (CRLF <-> LF)."""
    if to_lf:
        return content.replace(b"\r\n", b"\n")
    else:
        return content.replace(b"\n", b"\r\n").replace(b"\r\r\n", b"\r\n")


def deploy():
    """Deploy files to NAS via SFTP."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
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
        
        sftp = ssh.open_sftp()
        
        for local, remote in FILES_TO_DEPLOY:
            local_path = Path(local)
            
            if not local_path.exists():
                print(f"[-] SKIP {local}: file not found")
                continue
            
            print(f"[*] Uploading {local} -> {remote}...")
            
            content = local_path.read_bytes()
            
            # Normalize .sh files to LF
            if local.endswith(".sh"):
                content = normalize_line_endings(content, to_lf=True)
            
            # Write to temp file, then move
            temp_path = remote + ".tmp"
            sftp.putfo(paramiko.py3compat.BytesIO(content), temp_path)
            
            # Verify and move
            sftp._execute(f"mv {temp_path} {remote}")
            
            # Ensure executability for .sh files
            if local.endswith(".sh"):
                sftp._execute(f"chmod +x {remote}")
            
            print(f"[+] Uploaded {local}")
        
        sftp.close()
        
        # Restart services
        print("\n[*] Restarting trading-bot services on NAS...")
        stdin, stdout, stderr = ssh.exec_command(
            "systemctl restart trading-bot-stock trading-bot-train-hourly"
        )
        stdout.channel.recv_exit_status()
        
        print("[+] Services restarted")
        
        # Show status
        stdin, stdout, stderr = ssh.exec_command(
            "systemctl status trading-bot-stock trading-bot-train-hourly"
        )
        status = stdout.read().decode("utf-8")
        print("\nService Status:")
        print(status)
        
    except Exception as e:
        print(f"[!] ERROR: {e}")
        return False
    finally:
        ssh.close()
    
    return True


if __name__ == "__main__":
    if not deploy():
        sys.exit(1)
    print("\n✅ Deployment complete!")
