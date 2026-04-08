# Monitoring

Use the dashboard, logs, and daily reports to review how the system behaves during paper trading.

## Dashboard

The dashboard reads trade history from the running bots.

```bash
python dashboard.py
```

It shows:

- overall trade summary
- performance by symbol
- performance by day
- recent trades

## Logs

Review the generated log files regularly:

- `bot.log`
- `stock_bot.log`
- `backtest.log`

Look for:

- connection failures
- blocked orders
- repeated losses
- signal filtering problems
- webhook errors

## Daily Reports

Run the daily report when you want a compact operational summary.

```bash
python cli.py daily-report
```

The NAS daily profile job also sends a performance graph to Discord and records a local PNG in `logs/`.

## What to Watch

- trade frequency
- maximum drawdown
- win rate over a meaningful sample size
- profit factor
- repeated signal filtering
- daily profile changes and graph delivery status
