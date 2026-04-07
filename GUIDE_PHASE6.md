# Trading Bot - Phase 6 Complete Guide

Complete guide to running the trading bot with advanced features: Discord alerts, model retraining, and performance dashboards.

## Overview

This is a production-grade trading bot with:
- ✅ **Async crypto trading** (Binance via CCXT)
- ✅ **Paper stock trading** (Alpaca - real symbols, virtual money)
- ✅ **AI-powered decisions** (Random Forest with 12 features)
- ✅ **Risk management** (daily loss limits, position limits, ATR stops)
- ✅ **Real-time alerts** (Discord notifications)
- ✅ **Continuous learning** (automatic model retraining)
- ✅ **Performance tracking** (CSV logs + dashboard)

---

## Quick Start (5 Minutes)

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Edit `.env`:

```ini
# Binance (for crypto)
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_secret

# Alpaca (for stocks - get at https://app.alpaca.markets)
ALPACA_API_KEY=PK_...
ALPACA_API_SECRET=your_secret

# Discord (optional - for real-time alerts)
DISCORD_WEBHOOK_URL=https://discordapp.com/api/webhooks/YOUR_ID/YOUR_TOKEN

# Trading Config
MIN_AI_CONFIDENCE=0.45
MAX_DAILY_LOSS_PCT=5
MAX_OPEN_POSITIONS=2
MIN_TRADE_USDT=10
```

### 3. Run Stock Trading Bot (Recommended for Paper Trading)

```bash
python stock_bot.py
```

Expected output:
```
2024-01-16 10:30:00  INFO     🤖 Stock Bot started | Symbols: ['SPY', 'QQQ', 'VOO'] | 15min
2024-01-16 10:30:00  INFO     🧠 AI active | Trades: 42 | WR: 58%
2024-01-16 10:31:00  INFO     📊 SPY: RSI=35.2, volume_confirm=True, ATR_stop=$380.50
```

### 4. Monitor Performance

In another terminal:

```bash
python dashboard.py
```

Output:
```
============================================================
  🤖 TRADING PERFORMANCE DASHBOARD
============================================================

  Total trades loaded: 42
  Date range: 2024-01-10 to 2024-01-16

============================================================
  📊 OVERALL STATISTICS
============================================================

╒═══════════════════╤═══════════╕
│ Metric            │ Value     │
╞═══════════════════╪═══════════╡
│ Total Trades      │ 42        │
│ Wins              │ 24        │
│ Losses            │ 18        │
│ Win Rate          │ 57.1%     │
│ Total P&L         │ +12.45%   │
│ Avg Win           │ +1.23%    │
│ Avg Loss          │ -0.67%    │
│ Best Trade        │ +4.56%    │
│ Worst Trade       │ -2.34%    │
│ Profit Factor     │ 1.85      │
╘═══════════════════╧═══════════╛
```

---

## Features Explained

### Discord Alerts 🚨

Real-time notifications for every trade:

**Setup:**

1. Create Discord server/channel (if you don't have one)
2. Go to https://discord.com/developers/applications
3. Create "New Application" → "Trading Bot"
4. Go to "Settings" → "Webhooks" → "New Webhook"
5. Copy the webhook URL
6. Add to `.env`:
   ```ini
   DISCORD_WEBHOOK_URL=https://discordapp.com/api/webhooks/1234567890/AbCdEfGhIjKlMnOpQrStUvWxYz
   ```

**What you'll see:**

- 🟢 **Buy Alert**: Green embed with symbol, entry price, quantity, AI confidence
- 🔴 **Sell Alert**: Color-coded (green if profit, red if loss) with entry, exit, P&L %
- 📊 **Daily Summary**: Blue embed with trade count, win rate, daily P&L
- ⚠️ **Warnings**: Orange alerts for retraining, position limits
- 🔴 **Errors**: Red alerts for critical failures

Example Discord messages:

```
🟢 BUY: SPY
Entry: $420.50
Qty: 10
AI Confidence: 78%

🔴 SELL: SPY [+2.3%]
Entry: $420.50
Exit: $430.17
P&L: +$96.70 (+2.3%)
Reason: TAKE_PROFIT
```

### Model Retraining 🧠

Automatic AI learning from trading outcomes:

**How it works:**

1. Bot executes trades and logs outcomes to `trades_history.csv`
2. Every ~20 trades, model retrainer kicks in
3. Retraining loads recent trade history
4. New features extracted from past candles
5. Random Forest model refitted with new data
6. Model weights saved to `trading_model_rf.pkl`
7. Next trades use updated model

**View retraining status in logs:**

```
2024-01-16 10:35:00  INFO     🧠 Triggering model retraining...
2024-01-16 10:35:05  INFO     ✅ Model retraining complete
2024-01-16 10:35:05  INFO     🟢 Retraining: 20 trades analyzed
```

**Analytics from retraining:**

```python
retrainer = ModelRetrainer()
history = retrainer.load_trade_history()
summary = TradeAnalytics.get_summary(history)
print(f"Win Rate: {summary['win_rate']}%")
print(f"Total P&L: {summary['total_pnl']}%")
```

### Performance Dashboard 📊

Comprehensive trading performance analysis:

**Overall statistics:**

- Total trades, wins/losses, win rate
- Total P&L (%), average win/loss
- Best/worst trade, profit factor
- Risk metrics

**Breakdowns:**

- **By Symbol**: Performance for SPY, QQQ, VOO separately
- **By Day**: Daily performance tracking
- **Recent Trades**: Last 10 trades with details

**Run dashboard anytime:**

```bash
python dashboard.py
```

No database needed - reads from `trades_history.csv` (auto-generated).

---

## Trading Strategy

### Entry Conditions (All Must Pass)

1. **RSI Mean Reversion**
   - Price RSI < 30 (oversold) for 1+ candles
   - Price RSI rises above 30 (recovery signal)
   - ✅ Fix from Phase 4: was inverted, now correct

2. **Trend Filter**
   - Price must be above 200-period moving average (200 MA)
   - Prevents shorting falling knives

3. **Volume Confirmation**
   - 15-min candle volume > 20-candle average
   - Avoids illiquid moves

4. **AI Confidence**
   - Random Forest model must be ≥ 45% confident (configurable)
   - Uses 12 features: MACD, Bollinger Bands, price momentum, time-of-day, volume, RSI, trend
   - Lighter & faster than TensorFlow (1ms vs 50ms inference)

### Exit Conditions

1. **Trailing Stop Loss** (ATR-based)
   - Dynamic: 2x Average True Range
   - Adapts to volatility
   - Example: $380.50 for SPY if ATR=$1.50

2. **Take Profit**
   - Automatic exit at +2% gain
   - Locks in profits

3. **Cooldown After Loss**
   - After loss: Skip next 3 candles
   - Prevents revenge trading

### Risk Management

- **Max Daily Loss**: Stop trading if down 5% in a day
- **Max Positions**: Never more than 2 open positions
- **Min Trade Size**: Must be ≥ $10 (Alpaca minimum)
- **Position Sizing**: 1-10 shares depending on entry confidence

---

## File Structure

```
trading-bot/
├── stock_bot.py              # Main stock trading bot (Alpaca)
├── bot.py                    # Crypto trading bot (Binance)
├── strategy.py               # RSI + 200 MA (volume + ATR)
├── ml_model_rf.py            # Random Forest AI (12 features)
├── discord_alerts.py         # Discord webhook notifications
├── model_retrainer.py        # Automatic model retraining + analytics
├── dashboard.py              # Performance dashboard
├── stock_config.py           # Stock bot configuration
├── config.py                 # Crypto bot configuration
├── .env                      # API keys & settings (DO NOT COMMIT)
├── .env.example              # Template for .env
├── requirements.txt          # Python dependencies
├── trades_history.csv        # Auto-generated trade log
├── trading_model_rf.pkl      # Auto-generated RF model weights
└── README.md                 # This file
```

---

## Configuration

### `.env` Parameters

#### Required

```ini
# Alpaca (for stock trading)
ALPACA_API_KEY=PK_ABC123...
ALPACA_API_SECRET=your_secret_key

# Binance (for crypto trading) - optional
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
```

#### Optional with Defaults

```ini
# Strategy
MIN_AI_CONFIDENCE=0.45        # AI must be 45%+ confident (0.0-1.0)
OVERSOLD_RSI=30               # RSI below this = entry signal
OVERBOUGHT_RSI=70             # RSI above this = exit signal

# Risk Management
MAX_DAILY_LOSS_PCT=5          # Stop trading if down 5% daily
MAX_OPEN_POSITIONS=2          # Max 2 concurrent positions
MIN_TRADE_USDT=10             # Minimum $10 per trade

# Notifications (optional)
DISCORD_WEBHOOK_URL=          # None = Discord disabled (graceful)
LOG_LEVEL=INFO                # DEBUG, INFO, WARNING, ERROR

# Alpaca
ALPACA_BASE_URL=https://paper-api.alpaca.markets  # Paper trading (virtual)
# Use https://api.alpaca.markets for live trading (real money)
```

### Code Configuration

Edit `stock_config.py` to change:

```python
class StockConfig(BaseModel):
    symbols: List[str] = ["SPY", "QQQ", "VOO"]       # Symbols to trade
    timeframe: str = "15Min"                         # Candle size (15Min recommended)
    check_interval: int = 60                         # Seconds between checks
    lookback_candles: int = 200                      # For 200 MA + RSI calculation
    stop_loss_pct: float = 0.05                      # 5% fixed stop (ATR preferred)
    take_profit_pct: float = 0.02                    # 2% take profit
    trailing_stop_pct: float = 0.03                  # 3% trailing stop
    use_ai: bool = True                              # Use AI filtering
    paper_trading: bool = True                       # Virtual money (don't change to live!)
```

---

## Logs & Data

### Stock Bot Logs

Real-time logs in `stock_bot.log`:

```
2024-01-16 10:30:00  INFO     🤖 Stock Bot started | Symbols: ['SPY', 'QQQ', 'VOO'] | 15min
2024-01-16 10:30:00  INFO     🧠 AI active | Trades: 42 | WR: 58%
2024-01-16 10:31:00  INFO     📊 SPY: RSI=35.2, volume_confirm=True, ATR_stop=$380.50
2024-01-16 10:31:00  INFO     ✅ BUY: SPY @ $420.50 (10 shares, AI: 78%)
2024-01-16 10:32:00  INFO     ✅ SELL: SPY @ $430.17 (TAKE_PROFIT, +$96.70, +2.3%)
2024-01-16 10:35:00  INFO     🧠 Triggering model retraining...
2024-01-16 10:35:05  INFO     ✅ Model retraining complete
```

### Trade History CSV

Auto-generated `trades_history.csv`:

```csv
timestamp,symbol,side,entry_price,qty,ai_confidence,exit_reason,exit_price,pnl_usd,pnl_pct
2024-01-16 10:31:00,SPY,buy,420.50,10,0.78,,,,
2024-01-16 10:32:00,SPY,sell,420.50,10,0.78,TAKE_PROFIT,430.17,96.70,2.3%
2024-01-16 10:35:00,QQQ,buy,380.25,8,0.62,,,,
2024-01-16 10:36:00,QQQ,sell,380.25,8,0.62,TRAIL_STOP,378.10,-17.20,-0.6%
```

Use for analysis, backtesting, reporting.

### AI Model Files

- `trading_model_rf.pkl` - Random Forest model weights
- Auto-saved after retraining
- Auto-loaded on startup
- Size: ~200KB (vs TensorFlow's 50MB+)

---

## Troubleshooting

### "No API key found"

```
❌ BINANCE_API_KEY not set in .env
```

**Fix:** Add API keys to `.env`:

```bash
BINANCE_API_KEY=your_key_here
BINANCE_API_SECRET=your_secret_here
```

### "Discord webhook failed"

```
❌ Discord webhook error: 404
```

**Fix:**

1. Verify webhook URL is correct in `.env`
2. Webhook URLs can expire - regenerate from Discord dev portal
3. Bot will continue trading even if Discord fails (graceful)

### "Paper trading URL incorrect"

```
❌ Alpaca error: base_url https://api.alpaca.markets unauthorized
```

**Fix:** Use paper trading URL:

```ini
ALPACA_BASE_URL=https://paper-api.alpaca.markets
```

### "No trades yet"

```
Dashboard: "No trades yet."
```

**Fix:** 

1. Let bot run for at least 30-60 mins
2. Check logs to see if entries are being triggered
3. Verify AI confidence threshold isn't too high (try 0.30)

### "Model retraining not happening"

```
Logs don't show "🧠 Triggering model retraining..."
```

**Fix:**

1. Need at least 20 closed trades for retraining
2. Check `trades_history.csv` has entries
3. Verify `model_retrainer.py` exists and imports work

### "AttributeError: module 'ccxt' has no attribute..."

```
❌ ccxt.async_support not found
```

**Fix:** Using wrong CCXT for crypto bot:

```bash
pip install ccxt>=5.0.0
python bot.py  # Uses ccxt.async_support
```

---

## Advanced Usage

### Manual Model Retraining

```python
from ml_model_rf import TradingAI
from model_retrainer import ModelRetrainer

ai = TradingAI()
retrainer = ModelRetrainer(retrain_interval=20)

# Force retraining
retrainer.retrain_model(ai)
print("✅ Model retrained")
```

### Build Custom Strategy

Modify `strategy.py`:

```python
def get_signal_custom(close, high, low, volume):
    # Add your own indicators
    rsi = calculate_rsi(close)
    macd_line, signal_line = calculate_macd(close)
    
    # Custom entry signal
    if rsi < 30 and macd_line > signal_line:
        return "BUY"
    return "HOLD"
```

### Export Performance Report

```bash
python dashboard.py > report_2024_01_16.txt
```

### Run Crypto Bot Only

```bash
python bot.py
```

(Stock bot uses Alpaca, crypto bot uses Binance)

---

## Performance Expectations

### Realistic Targets

- **Win Rate**: 55-65% (not 100%)
- **Risk/Reward**: 1:1.5 (win 1.5% vs lose 1%)
- **Drawdown**: 5-15% dips are normal
- **Monthly**: +5-15% good, +20%+ excellent

### Factors Affecting Performance

- **Market conditions**: Trending vs choppy
- **Settings**: AI confidence, stop loss sizes
- **Symbols**: SPY vs speculative small-caps
- **Volatility**: High VIX = more false signals

### Safety Features

- **Max daily loss**: Stops trading if down 5%
- **Position sizing**: Smaller trades = less risk
- **Take profit**: Forces discipline (2% gains add up)
- **Trailing stops**: Protects against reversals

---

## Next Steps

1. ✅ Deploy stock bot with Discord alerts
2. ✅ Let it trade 30-60 mins to generate trade history
3. ✅ Run dashboard to review performance
4. ✅ Adjust AI confidence or symbols based on results
5. 🔄 Monitor logs daily
6. 📊 Review trades weekly
7. 🧠 Model retrains automatically

---

## Roadmap (Future Enhancements)

- [ ] Web dashboard (real-time charts, P&L)
- [ ] Telegram alerts (in addition to Discord)
- [ ] Email reports (daily summary)
- [ ] Hyperparameter optimization (auto-tune settings)
- [ ] Multi-timeframe analysis (5min + 15min + 1hour)
- [ ] Options trading support
- [ ] Live money trading (currently paper only)
- [ ] Backtesting engine

---

## Support

### Bugs/Issues

Check the logs first:

```bash
tail -f stock_bot.log
```

### Questions?

Review the code comments:

```python
# All functions have docstrings explaining logic
```

---

**Happy trading! 🚀**

*Disclaimer: This is educational software. Past performance ≠ future results. Always trade with capital you can afford to lose.*
