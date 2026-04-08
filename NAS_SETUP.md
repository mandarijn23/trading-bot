# NAS Setup Guide

This guide shows how to run the stock paper-trading bot on Ubuntu NAS so it starts before market open, runs during market hours, and shuts itself down at the close.

## What the bot now does

- Waits for the NYSE session to open
- Trades only during the session
- Retrains the model at end of day when enabled
- Closes open positions at market close
- Exits cleanly so systemd or cron can restart it next session

## What Copilot can and cannot do

Copilot can help you:

- Generate scripts, systemd units, cron jobs, and config files
- Explain how to deploy them on Ubuntu
- Review logs and suggest fixes when you paste the output here

Copilot cannot directly log in to your NAS or control it autonomously from this chat. If you expose the NAS via SSH and run commands in your own environment, I can help you build the exact commands and files.

## Free AI Options For NAS Control

If you want a free AI to help control the NAS, the realistic options are:

- `Ollama` running a local model such as `Qwen2.5`, `Llama 3.1`, or `Phi-3`
- `Open Interpreter` for shell-driven automation with human confirmation
- `Aider` for code and file edits, not full NAS administration
- `Ansible` with a local or remote LLM assisting the playbook steps

My recommendation is a local model + SSH or Ansible, not a fully autonomous agent with unchecked sudo access.

Safe pattern:

1. AI suggests the command or playbook step.
2. You approve it.
3. The command runs over SSH or Ansible.
4. Logs are reviewed before the next step.

That gives you useful automation without handing the NAS over to a black box.

### Recommended lightweight model path

Your NAS has a Ryzen 5 3600, 15 GiB RAM, and no GPU, so start with `Qwen2.5 3B` and keep `Phi-3 Mini` as the fallback.

Use these commands on the NAS:

```bash
./nas_copilot.sh /home/nas/trading-bot ai-bootstrap
./nas_copilot.sh /home/nas/trading-bot ai-test
./nas_copilot.sh /home/nas/trading-bot ai-status
```

If `ollama` is not installed yet, `ai-bootstrap` will install it and pull the models for you.

From your Windows workstation, you can run everything in one command:

```powershell
powershell -ExecutionPolicy Bypass -File .\nas_remote_bootstrap.ps1
```

Optional custom host/path:

```powershell
powershell -ExecutionPolicy Bypass -File .\nas_remote_bootstrap.ps1 -NasHost nas@192.168.1.70 -AppDir /home/nas/trading-bot
```

## Recommended setup

### 1. Put the repo on the NAS

Example location:

```bash
/opt/trading-bot
```

### 2. Create a virtual environment

```bash
cd /opt/trading-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-stock.txt
```

### 3. Create `.env`

Use your Alpaca paper keys and stock settings. The stock path expects these core values:

```env
ALPACA_API_KEY=your_key
ALPACA_API_SECRET=your_secret
ALPACA_BASE_URL=https://paper-api.alpaca.markets
STOCK_SYMBOLS=["SPY","QQQ","VOO"]
STOCK_TIMEFRAME=15Min
STOCK_PAPER_TRADING=true
```

### 4. Validate the setup

```bash
python validate_setup.py
python paper_launch_check.py --mode stocks
```

Both should pass before you enable automation.

### 5. Recommended: install the cron schedule

Because your NAS is currently set to UTC, the cleanest approach is a cron job that uses `CRON_TZ=America/New_York` so the bot starts on US market time regardless of the NAS clock.

Add this to the NAS user's crontab:

```cron
CRON_TZ=America/New_York
25 9 * * 1-5 cd /home/nas/trading-bot && ./run_stock_session.sh >> stock_session.log 2>&1
20 16 * * 1-5 cd /home/nas/trading-bot && ./.venv/bin/python daily_performance_report.py >> daily_performance_report.log 2>&1
```

If you prefer `systemd`, use the NAS-specific units in `systemd/nas/`. Cron is easier to keep timezone-safe on a UTC NAS, but systemd is better for clean service management.

### 6. NAS-specific systemd option

If you want `systemd`, install these two files instead of the generic service:

- `systemd/nas/trading-bot-stock.service`
- `systemd/nas/trading-bot-stock.timer`

They are already tuned for:

- `/home/nas/trading-bot`
- user `nas`
- a start time that is safely before US market open, so the bot waits for the bell

### 7. Optional: install the systemd service and timer

Copy the unit files from `systemd/` into your system directory:

```bash
sudo cp systemd/trading-bot-stock.service /etc/systemd/system/
sudo cp systemd/trading-bot-stock.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable trading-bot-stock.timer
sudo systemctl start trading-bot-stock.timer
```

### 8. Update the service paths and user

Edit `/etc/systemd/system/trading-bot-stock.service` and set:

- `WorkingDirectory` to your repo path on the NAS
- `ExecStart` to the full path of `run_stock_session.sh`
- `User` and `Group` to the Linux account that owns the repo

Example:

```ini
WorkingDirectory=/home/ivart/trading-bot
ExecStart=/home/ivart/trading-bot/run_stock_session.sh
User=ivart
Group=ivart
```

### 9. Check timer status

```bash
systemctl list-timers trading-bot-stock.timer
systemctl status trading-bot-stock.timer
journalctl -u trading-bot-stock.service -f
```

## Daily workflow

- Bot starts automatically at 09:25 Monday through Friday
- It waits if the market is not open yet
- It trades during the session
- It exits and closes positions at market close
- Review `stock_bot.log` and `trades_history.csv` after the session
- Run the daily report:

```bash
python daily_performance_report.py
```

## If you want a cron alternative

You can use the example in `nas_stock_cron.example`, and it is the recommended choice when your NAS timezone is not US/Eastern.

## Troubleshooting

- If the bot does not start, check `journalctl -u trading-bot-stock.service -f`
- If Alpaca rejects the connection, verify the paper API keys in `.env`
- If the bot starts but does not trade, it may simply be waiting for a valid signal or insufficient bars
- If the stock market hours are wrong, verify the NAS timezone is set correctly to your local region or leave the bot on US/Eastern logic and use the market calendar helper
