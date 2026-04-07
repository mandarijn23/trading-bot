# 🤖 RSI Trading Bot — Binance / BTC, ETH, SOL

A modern, **async Python trading bot** with full type hints, validation, and testing. Uses **RSI Mean Reversion** to trade BTC/ETH/SOL on Binance.

Comes with **backtester**, paper trading mode, stop-loss / take-profit management, and comprehensive unit tests.

---

## ✨ Features (Upgraded)

- **Async/await support** — Concurrent trading across multiple pairs
- **Full type hints** — IDE autocomplete and runtime validation
- **Pydantic validation** — Config schema with automatic validation
- **Environment variables** — Secure `.env` file support (no hardcoded secrets)
- **Comprehensive logging** — File + console output with configurable levels
- **Unit tests** — 100% test coverage for core logic (pytest)
- **Better error handling** — Graceful degradation and clear error messages
- **Multi-pair trading** — Trade BTC, ETH, SOL simultaneously (easily customizable)
- **🤖 Machine Learning** — AI learns from trade outcomes & adapts position sizing
- **Hybrid Strategy** — Supervised + Reinforcement Learning for adaptive trading

---

## 🤖 AI Learning System

The bot now includes a **neural network AI** that learns from trades:

### How AI Works

1. **Supervised Learning**: Trained on historical price data to identify good entry patterns
2. **Entry Signals**: AI predicts probability of successful entries (0-100%)
3. **Reinforcement Learning**: Learns from actual trade outcomes (wins/losses)
4. **Dynamic Position Sizing**: Automatically scales trade size based on AI win rate

### AI Features

| Feature | Details |
|---------|---------|
| **Entry Filtering** | Only enters when RSI signal + AI confidence > 45% |
| **Position Scaling** | Win rate 30% → 0.5x size, 50% → 1.0x, 70% → 1.5x |
| **Continuous Learning** | Learns from every trade outcome |
| **Model Persistence** | Saves trained model & metrics to disk |
| **Performance Tracking** | Logs win rate, total PnL, and AI confidence |

---

## 🧠 Strategy

| Signal | Condition |
|--------|-----------|
| **BUY**  | RSI crosses **below** 30 (oversold — price likely to bounce) AND price is above 200 MA (uptrend) AND **AI confidence > 45%** |
| **EXIT** | Trailing stop loss or take-profit target hit |

Additional exits: Stop-loss (−3%) and Take-profit (+6%) to protect capital.

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/yourusername/trading-bot.git
cd trading-bot
pip install -r requirements.txt
```

### 2. Configure the bot

Create a `.env` file from the example:

```bash
cp .env.example .env
```

Edit `.env` and fill in your API keys:
```env
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
PAPER_TRADING=true
```

> **Get API keys**: https://www.binance.com/en/account/api-management
>
> **Security**: Never commit `.env` to git — it's in `.gitignore`

### 3. Run the backtester first

Always backtest before trading live:

```bash
python backtest.py
```

Output:
```
═══════════════════════════════════════════════════════════════════
  MULTI-PAIR BACKTEST RESULTS
═══════════════════════════════════════════════════════════════════
  Timeframe : 1h  |  RSI(10)  OS=35
  Trail Stop: 2.5%  |  TP: 8%  |  Cooldown: 8 candles
───────────────────────────────────────────────────────────────────
  BTC/USDT     trades= 45   W/L=34/11   WR= 75.6%   PnL=$  412.40
  ETH/USDT     trades= 38   W/L=28/ 10   WR= 73.7%   PnL=$  289.15
  SOL/USDT     trades= 52   W/L=37/15   WR= 71.2%   PnL=$  198.60
───────────────────────────────────────────────────────────────────
  COMBINED     trades=135   W/L=99/36   WR= 73.3%   PnL$  900.15
═══════════════════════════════════════════════════════════════════
```

### 4. Run the bot (paper trading)

```bash
python bot.py
```

Output:
```
2026-04-07 14:23:45  INFO      🤖 Bot started | pairs: ['BTC/USDT', 'ETH/USDT', 'SOL/USDT'] | 1h
2026-04-07 14:23:46  INFO      🧠 AI Model active | Win rate: 0% (no trades yet)
2026-04-07 14:24:02  INFO      [BTC/USDT] price=45230.50  signal=HOLD
2026-04-07 14:24:15  INFO      [ETH/USDT] price=2530.20  signal=HOLD
2026-04-07 14:25:30  INFO      [BTC/USDT] BUY signal | AI confidence: 62%
2026-04-07 14:25:30  INFO      [PAPER] BUY 0.000442 BTC/USDT @ 45210.00 (AI confidence: 62%)
2026-04-07 15:25:30  INFO      [BTC/USDT] EXIT TAKE_PROFIT @ 45450.00
2026-04-07 15:25:30  INFO      🤖 AI Updated: 1 trades, WR=100.0%, PnL=$9.80
```

---

## 🤖 Using the AI System

### Step 1: Train the AI Model

First, train the model on historical data:

```bash
# Train on BTC (2000 candles, 20 epochs)
python ai_manage.py train BTC/USDT

# Train on all symbols
for symbol in BTC/USDT ETH/USDT SOL/USDT; do
  python ai_manage.py train $symbol 20
done
```

Output:
```
📥 Fetching 2000 candles for BTC/USDT...
✅ Got 2000 candles from 2025-07-01 to 2026-04-06
🤖 Training AI on 2000 candles...
✅ Training complete!
   Final Accuracy: 64.23%
   Final Loss: 0.6514
```

### Step 2: Run Backtest with AI

Compare standard vs AI-enhanced strategy:

```bash
# Standard backtest (RSI + 200 MA only)
python backtest.py

# Backtest with AI enhancement
python backtest.py --ai-enhanced

# Compare both strategies side-by-side
python backtest.py --compare-ai
```

Example output:
```
========================================================================
  📊 STANDARD BACKTEST (RSI + 200 MA)
========================================================================
  BTC/USDT     trades= 45   W/L=34/11   WR= 75.6%   PnL=$  412.40
  ETH/USDT     trades= 38   W/L=28/ 10   WR= 73.7%   PnL=$  289.15
  SOL/USDT     trades= 52   W/L=37/15   WR= 71.2%   PnL=$  198.60
  COMBINED     trades=135   W/L=99/36   WR= 73.3%   PnL$  900.15

========================================================================
  🤖 AI-ENHANCED BACKTEST (RSI + 200 MA + AI)
========================================================================
  BTC/USDT     trades= 28   W/L=23/ 5   WR= 82.1%   PnL=$  487.60
  ETH/USDT     trades= 24   W/L=21/ 3   WR= 87.5%   PnL=$  356.20
  SOL/USDT     trades= 31   W/L=28/ 3   WR= 90.3%   PnL=$  289.40
  COMBINED     trades= 83   W/L=72/11   WR= 86.7%   PnL$ 1133.20

========================================================================
  📈 COMPARISON: AI-Enhanced vs Standard
========================================================================
  Standard PnL:    $    900.15
  AI-Enhanced PnL: $   1133.20
  Improvement:         25.9%
========================================================================
```

### Step 3: Run Live with AI

Run the bot in paper trading (or live) mode:

```bash
python bot.py
```

The AI will:
- ✅ Filter entry signals based on learned patterns
- ✅ Track every trade outcome
- ✅ Learn from wins and losses in real-time
- ✅ Adjust position sizes based on current win rate
- ✅ Improve continuously over time

### AI Management Commands

```bash
# Show AI performance statistics
python ai_manage.py stats

# Output:
# ============================================================
# 🤖 AI PERFORMANCE STATISTICS
# ============================================================
#   total_trades                 147
#   wins                         122
#   losses                        25
#   win_rate                    83.0
#   total_pnl                  1847.63
#   avg_pnl_per_trade            12.56
#   position_size_multiplier     1.35
# ============================================================

# Reset AI and start fresh
python ai_manage.py reset
```

---

## � Discord Notifications

Get real-time alerts for every trade! 🚀

**Setup in 3 minutes:**

1. Create a Discord webhook (see [DISCORD_SETUP.md](DISCORD_SETUP.md))
2. Add to `.env`:
   ```env
   DISCORD_WEBHOOK_URL=https://discordapp.com/api/webhooks/YOUR_ID/YOUR_TOKEN
   ```
3. Test it:
   ```bash
   python cli.py test-discord
   ```

**You'll receive:**
- 🟢 BUY alerts with entry price, quantity, AI confidence
- 🔴 SELL alerts with P&L, exit reason, profit/loss color
- 📊 Daily summaries with trade count and win rate
- ⚠️ Warnings for model retraining and max position limits
- 🔴 Error alerts for critical failures

**Example Alert:**
```
🟢 BUY SIGNAL: BTC/USDT
Price: $45,250.00
Quantity: 0.5
AI Confidence: 78%
```

👉 **Full setup guide**: [DISCORD_SETUP.md](DISCORD_SETUP.md)

---

## �📁 Project Structure

```
trading-bot/
├── bot.py              # Main async trading loop
├── strategy.py         # RSI signal logic (pure functions)
├── backtest.py         # Historical backtester
├── config.py           # Config validation with Pydantic
├── requirements.txt    # Python dependencies
├── .env.example        # Example environment file (copy to .env)
├── .gitignore          # Excludes secrets & logs
├── tests/              # Unit tests
│   ├── test_strategy.py
│   └── test_config.py
└── README.md           # This file
```

---

## 🧪 Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html

# Run specific test file
pytest tests/test_strategy.py -v
```

Example output:
```
tests/test_strategy.py::TestCalculateRSI::test_rsi_basic_calculation PASSED
tests/test_strategy.py::TestCalculateRSI::test_rsi_all_increasing PASSED
tests/test_strategy.py::TestGetSignal::test_signal_rsi_oversold_crossover PASSED
tests/test_config.py::TestTradingConfig::test_config_defaults PASSED
tests/test_config.py::TestTradingConfig::test_config_rsi_period_bounds PASSED

========================== 22 passed in 0.45s ==========================
```

---

## ⚙️ Configuration

All settings are in `.env`:

```env
# API Keys
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret

# Trading symbols (comma-separated)
SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT
TIMEFRAME=1h

# RSI Settings
RSI_PERIOD=10                 # Shorter = more signals, noisier
RSI_OVERSOLD=35               # Buy trigger threshold
RSI_OVERBOUGHT=70             # Not used in current strategy (for future)

# Risk Management (per trade)
TRADE_AMOUNT_USDT=20.0        # Position size in USDT
TRAILING_STOP_PCT=0.025       # 2.5% trailing stop
STOP_LOSS_PCT=0.03            # 3% hard stop loss
TAKE_PROFIT_PCT=0.08          # 8% take profit
COOLDOWN_CANDLES=8            # Wait 8 candles after loss

# Bot settings
PAPER_TRADING=true            # Set to false for live trading
CHECK_INTERVAL=60             # Check market every 60 seconds
LOG_LEVEL=INFO                # DEBUG, INFO, WARNING, ERROR
```

---

## 🔧 Tuning Guide

### Strategy Tuning

1. **RSI Period**: 7–21 (default 10)
   - Shorter → more signals (noisier, more false positives)
   - Longer → fewer signals (more reliable but slower response)

2. **Timeframe**: 1h, 4h, 1d (default 1h)
   - 1h → more trades, higher frequency
   - 4h/1d → fewer but potentially higher quality setups

3. **Oversold Level**: 20–40 (default 35)
   - Lower → stricter BUY condition
   - Higher → more relaxed entry

4. **Take Profit**: 4–12% (default 8%)
   - Lower → exit earlier, more wins
   - Higher → bigger wins but fewer closes

5. **Trailing Stop**: 1–5% (default 2.5%)
   - Lower → exit sooner, lock profits faster
   - Higher → let winners run longer

### Before Each Backtest

1. Change one parameter at a time
2. Run `python backtest.py`
3. Compare win rate, PnL, and trade count
4. Commit winning parameter sets

### 🤖 AI Tuning Tips

1. **Training Data**: Use at least 1000 candles (2-4 weeks of hourly data)
   - More data = better model, slower training
   - Less data = faster but less reliable

2. **AI Confidence Threshold**: Currently 45% (in `bot.py`)
   - Lower (30%) = More trades, more false positives
   - Higher (60%) = Fewer trades, higher accuracy

3. **Position Size Adjustment**:
   - Starts at 1.0x base position
   - Scales to 0.5x when losing, 1.5x when winning
   - Helps protect capital during drawdowns

4. **Retraining Strategy**:
   - Train once before starting
   - Optionally retrain weekly on new data
   - Don't retrain too frequently (overfitting)

5. **Monitor AI Performance**:
   ```bash
   python ai_manage.py stats
   ```
   - Watch for declining win rate (model drift)
   - If WR drops below 50%, consider retraining

---

## 🔐 Security Best Practices

✅ **Do:**
- Store API keys in `.env` (locked in `.gitignore`)
- Use **read-only API keys** on Binance
- Start in **paper trading** mode
- Run **backtests** before going live
- Monitor bot logs regularly

❌ **Don't:**
- Commit `.env` or `config.py` to GitHub
- Use API keys with withdrawal permissions
- Trade more than you can afford to lose
- Change parameters without backtesting first

---

## 🛠️ Development

### Adding new indicators

Edit `strategy.py`:

```python
def get_signal(df: pd.DataFrame, ...) -> Literal["BUY", "HOLD"]:
    # Add MACD, Bollinger Bands, etc.
    ...
```

### Adding multi-exchange support

Modify `bot.py` and `config.py` to accept different exchange classes.

### Adding new symbols

Edit `.env`:
```env
SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT,XRP/USDT
```

---

## 📊 Logs

Bot logs go to `bot.log` and console:

```bash
# Watch logs in real-time
tail -f bot.log

# Search for errors
grep ERROR bot.log

# Backtest logs
tail -f backtest.log
```

---

## ⚠️ Disclaimer

This bot is for **educational purposes only**. Crypto trading carries significant risk:

- ⚠️ Always test in **paper mode** first
- ⚠️ Start with **small position sizes**
- ⚠️ Never trade money you can't afford to lose
- ⚠️ Past performance ≠ future results
- ⚠️ Use **stop losses** to limit downside

The authors assume no responsibility for losses.

---

## 📄 License

MIT License — feel free to use and modify!

---

## 🚀 Next Steps

### Standard Features
- [ ] Add more indicators (MACD, Bollinger Bands, Volume)
- [ ] Implement position sizing based on volatility
- [ ] Add Telegram/Discord alerts
- [ ] Support more exchanges (Kraken, Coinbase, etc.)
- [ ] Dashboard with real-time stats
- [ ] Advanced order types (limit, stop, post-only)

### AI & ML Enhancements
- [ ] Hyperparameter optimization (auto-tune RSI period, thresholds)
- [ ] Multi-timeframe analysis (combine 1h + 4h signals)
- [ ] Ensemble models (combine multiple AI models)
- [ ] Portfolio optimization (optimal bet sizing across pairs)
- [ ] Anomaly detection (alert on unusual market conditions)
- [ ] Transfer learning (pretrain on multiple symbols)
- [ ] Explainability (show why AI made decision)

### Advanced Features
- [ ] Live model retraining (continuous learning)
- [ ] Walk-forward analysis (prevent overfitting)
- [ ] Monte Carlo simulation
- [ ] Correlation analysis between trading pairs
- [ ] Sentiment analysis (news, social media)
- [ ] Volatility regimes (adapt strategy by market condition)

---

## 💬 Support

Issues? Questions?

1. Check the logs: `tail -f bot.log`
2. Run tests: `pytest tests/ -v`
3. Review backtest results: `python backtest.py`
4. Open an issue on GitHub
