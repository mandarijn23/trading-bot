# Trading Bot

A Python trading system for research, paper trading, and controlled live deployment. The project includes strategy logic, ML-assisted filtering, backtesting, a dashboard, Discord notifications, and operational tooling.

## Overview

The repository is organized around a stock trading workflow with shared strategy and support modules:

- `core/` contains the main bot implementations.
- `strategies/` contains the strategy engine and indicator logic.
- `models/` contains machine learning models and training helpers.
- `utils/` contains portfolio, risk, market-hours, and notification helpers.
- `tools/` contains launch, validation, deployment, and reporting scripts.
- `tests/` contains automated checks for the strategy, models, and trading flows.

The current operating mode is paper trading first. The code is structured to make strategy changes testable before using them in a real account.

## Key Capabilities

- Strategy execution with RSI, trend, volatility, and volume filters
- ML-assisted trade scoring and retraining support
- Risk controls for position sizing, loss limits, and trade gating
- Paper-trading and live-trading configuration support
- Performance logging and daily reporting
- Discord webhook alerts
- Dashboard for recent trades and runtime status
- Automated tests and validation scripts

## Recommended Entry Points

- `python trade.py` for the interactive launcher
- `python cli.py validate-config` to verify configuration
- `python cli.py preflight` for the paper-trading launch checklist
- `python cli.py daily-report` for a performance and decay summary
- `python dashboard.py` for the performance dashboard
- `tools/install_nas_stack.sh` to install and enable the full NAS stack

## Setup

1. Install dependencies.

```bash
pip install -r requirements.txt
```

2. Create the local environment file.

```bash
cp .env.example .env
```

3. Add the required API keys and runtime settings for the workflow you plan to run.

4. Validate the configuration.

```bash
python cli.py validate-config
```

## Monitoring

Use the dashboard and logs to review live behavior:

- `dashboard.py` for performance and recent trades
- `bot.log` and `stock_bot.log` for execution logs
- `logs/` for generated reports and run history
- `cli.py stats` for model and trade analytics
- `tools/send_performance_graph.py` for the Discord performance graph
- `tools/rotate_stock_profile.sh` for the 2-day aggressive / 2-day normal profile cycle
- `tools/daily_profile_graph.sh` for the daily profile rotation plus graph push

## Safety Notes

- Start in paper trading mode.
- Verify API credentials before running any launch command.
- Review the dashboard and logs before changing strategy parameters.
- Do not assume backtest results will transfer directly to live trading.

## Documentation

- [Setup guide](docs/setup.md)
- [Monitoring guide](docs/monitoring.md)
- [Dashboard guide](docs/dashboard.md)

