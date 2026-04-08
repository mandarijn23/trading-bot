# Setup

This guide covers the minimum steps required to prepare the trading system for paper-trading validation.

## Requirements

- Python 3.8 or newer
- `pip` for dependency installation
- A local `.env` file
- Broker or exchange credentials for the bot you plan to use

## Install Dependencies

```bash
pip install -r requirements.txt
```

## Configure Environment

Create the local environment file from the example.

```bash
cp .env.example .env
```

Then add the required values for the workflow you plan to run.

### Common settings

- `LOG_LEVEL`
- `DISCORD_WEBHOOK_URL` if notifications are enabled

### Trading settings

- API credentials for the selected broker or exchange
- Symbols or watchlist configuration
- Paper-trading flag for the selected workflow
- Risk limits and sizing settings

## Validate

Run the built-in checks before starting a live or paper session.

```bash
python cli.py validate-config
python cli.py preflight
```

## Recommended Startup Order

1. Install dependencies.
2. Create and fill `.env`.
3. Run `python cli.py validate-config`.
4. Run `python cli.py preflight`.
5. Start the launcher with `python trade.py`.
