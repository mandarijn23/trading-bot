# NAS AI Assistant Guide

This guide shows the safest way to give your NAS a free AI helper that can diagnose issues and apply approved fixes.

## Recommended stack

- `Ollama` for a local LLM
- `Open Interpreter` or `Ansible` for command execution
- SSH access to the NAS
- A human approval step before changes are applied

## Best free models

Good local options for a NAS helper:

- `Qwen2.5 3B`
- `Phi-3 Mini`
- `Llama 3.2 3B`

Based on your NAS specs, start with a lightweight 3B model. You have an `AMD Ryzen 5 3600` and `15 GiB RAM` with no GPU, so the best fit is:

- primary choice: `Qwen2.5 3B`
- fallback: `Phi-3 Mini`

Avoid 7B+ models unless you are happy with slower response times.

Suggested Ollama pulls:

```bash
ollama pull qwen2.5:3b
ollama pull phi3:mini
```

## What the AI can do safely

- Read logs
- Suggest commands
- Run health checks
- Restart services when you approve
- Reinstall dependencies with your approval
- Re-run the paper preflight

## What it should not do blindly

- Delete files without approval
- Run `sudo` commands without a prompt
- Change firewall or network settings without a review step
- Place live trades automatically after a failure

## A safe repair loop

Use these scripts on the NAS:

- `nas_health_check.sh` - checks service state, disk space, and preflight status
- `nas_repair.sh` - re-runs health checks and restarts the trading service if needed
- `nas_copilot.sh` - an allowlisted command wrapper for approved actions only
- `nas_ai_bootstrap.sh` - installs Ollama, pulls the lightweight models, and runs a quick test prompt

## Recommended copilot workflow script

Use `nas_copilot.sh` when the AI suggests a fix.

Example actions:

```bash
./nas_copilot.sh /home/nas/trading-bot status
./nas_copilot.sh /home/nas/trading-bot health
./nas_copilot.sh /home/nas/trading-bot preflight
./nas_copilot.sh /home/nas/trading-bot ai-bootstrap
./nas_copilot.sh /home/nas/trading-bot ai-status
./nas_copilot.sh /home/nas/trading-bot ai-test
./nas_copilot.sh /home/nas/trading-bot ai-pull-primary
./nas_copilot.sh /home/nas/trading-bot repair
./nas_copilot.sh /home/nas/trading-bot logs
```

It will show the exact command and require `YES` before it runs anything that changes the NAS.

## How to set up Ollama on Ubuntu NAS

### 1. Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 2. Pull a model

```bash
ollama pull qwen2.5:3b
ollama pull phi3:mini
```

### 3. Test it

```bash
ollama run qwen2.5:3b "Summarize the state of my trading bot and suggest the next repair step."
```

### 4. Bootstrap from the repo

From the NAS repo root, you can run the allowlisted bootstrap action:

```bash
./nas_copilot.sh /home/nas/trading-bot ai-bootstrap
```

From your Windows workstation, run the remote helper to do bootstrap + test + status in one step:

```powershell
powershell -ExecutionPolicy Bypass -File .\nas_remote_bootstrap.ps1
```

## How to connect AI to the NAS

### Option A: Open Interpreter

This is the easiest free route if you want the AI to suggest shell commands interactively.

```bash
pipx install open-interpreter
interpreter
```

Then point it at the NAS over SSH, and require confirmation before execution.

### Option B: Ansible + local AI

Use the AI to generate or edit an Ansible playbook, then run the playbook yourself.

### Option C: SSH command helper

Have the AI read logs, choose a fix from a predefined list, and run only approved commands like:

- `systemctl restart trading-bot-stock.service`
- `./nas_health_check.sh`
- `./paper_launch_check.py --mode stocks`

## Recommended operating pattern

1. AI reads logs or service status.
2. AI proposes a repair.
3. AI prints the exact `nas_copilot.sh` action.
4. You approve the repair by typing `YES`.
5. Script runs on the NAS.
6. AI rechecks the result.

## Example repair flow

```bash
cd /home/nas/trading-bot
./nas_health_check.sh
./nas_repair.sh
```

## If you want maximum safety

Keep the AI as a helper, not a root shell.

A good setup is:

- AI on the NAS itself via Ollama
- SSH into the NAS
- Only approved repair scripts are executable
- systemd handles the bot lifecycle
- AI handles diagnosis and suggestions

If you want the fastest path, install `qwen2.5:3b` first, verify it with `ai-test`, and only then keep `phi3:mini` as the fallback.

## If you want to make it more automatic later

I can help you build:

- a log-watching agent that reads `journalctl`
- a repair queue that only executes pre-approved actions
- a daily summary bot that emails you when a repair happened
