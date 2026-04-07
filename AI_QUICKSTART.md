# 🤖 AI Trading Bot — Quick Start Guide

This guide walks you through setting up and using the Machine Learning-enhanced trading bot.

---

## 📋 Prerequisites

```bash
# Check you have Python 3.9+
python --version

# Navigate to bot directory
cd trading-bot

# Install dependencies
pip install -r requirements.txt
```

---

## 🚀 1. Configure the Bot (5 minutes)

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your API keys
nano .env
```

Required settings in `.env`:
```env
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
PAPER_TRADING=true  # Always start with paper trading!
```

Get API keys: https://www.binance.com/en/account/api-management

---

## 🧪 2. Test Without AI (10 minutes)

First, backtest the standard RSI strategy:

```bash
python backtest.py
```

Sample output:
```
═══════════════════════════════════════════════════════════════════
  MULTI-PAIR BACKTEST RESULTS
═══════════════════════════════════════════════════════════════════
  BTC/USDT     trades= 45   W/L=34/11   WR= 75.6%   PnL=$  412.40
  ETH/USDT     trades= 38   W/L=28/ 10   WR= 73.7%   PnL=$  289.15
  SOL/USDT     trades= 52   W/L=37/15   WR= 71.2%   PnL=$  198.60
  COMBINED     trades=135   W/L=99/36   WR= 73.3%   PnL$  900.15
═══════════════════════════════════════════════════════════════════
```

---

## 🤖 3. Train the AI Model (5-10 minutes)

Now train the neural network on historical data:

```bash
# Train on BTC (2000 candles, 20 epochs)
python ai_manage.py train BTC/USDT 20

# Train on all symbols
for symbol in BTC/USDT ETH/USDT SOL/USDT; do
  python ai_manage.py train $symbol 20
done
```

The AI will:
- 📥 Fetch 2000 recent candles for each symbol
- 🧠 Extract price action features
- 🎓 Train a neural network to predict good entries
- 💾 Save the model to `trading_model.h5`

Expected output:
```
📥 Fetching 2000 candles for BTC/USDT...
✅ Got 2000 candles from 2025-07-01 to 2026-04-06
🤖 Training AI on 2000 candles...
✅ Training complete!
   Final Accuracy: 64.23%
   Final Loss: 0.6514
```

---

## 🔬 4. Backtest with AI (5 minutes)

Now compare the AI-enhanced strategy against the standard strategy:

```bash
# Run side-by-side comparison
python backtest.py --compare-ai
```

This will show:
1. ✅ **Standard Results** (RSI + 200 MA only)
2. 🤖 **AI Results** (RSI + 200 MA + AI confidence filter)
3. 📈 **Comparison** (Performance improvement %)

Example output:
```
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

If AI shows improvement → continue to step 5.
If not → try `ai_manage.py train <symbol> 30` with more epochs.

---

## ▶️ 5. Run the Bot Live (Paper Trading)

Start trading in paper mode (no real money):

```bash
python bot.py
```

The bot will:
- 🔄 Monitor BTC, ETH, SOL every 60 seconds
- 📊 Check for RSI oversold signals + AI confirmation
- 🎯 Enter trades when both signal and AI agree
- 📈 Manage positions with trailing stops
- 🧠 Learn from every trade outcome
- 📊 Scale position sizes based on AI win rate

Live log output:
```
2026-04-07 14:23:45  INFO      🤖 Bot started | pairs: ['BTC/USDT', 'ETH/USDT', 'SOL/USDT'] | 1h
2026-04-07 14:23:46  INFO      🧠 AI Model active | Win rate: 0% (no trades yet)
2026-04-07 14:25:30  INFO      [BTC/USDT] BUY signal | AI confidence: 62%
2026-04-07 14:25:30  INFO      [PAPER] BUY 0.000442 BTC/USDT @ 45210.00 (AI confidence: 62%)
2026-04-07 15:25:30  INFO      [BTC/USDT] EXIT TAKE_PROFIT @ 45450.00
2026-04-07 15:25:30  INFO      🤖 AI Updated: 1 trades, WR=100.0%, PnL=$9.80
```

Watch logs in real-time:
```bash
tail -f bot.log
```

---

## 📊 6. Monitor AI Performance

Check AI statistics while bot is running (in another terminal):

```bash
python ai_manage.py stats
```

Output:
```
============================================================
🤖 AI PERFORMANCE STATISTICS
============================================================
  total_trades                 147
  wins                         122
  losses                        25
  win_rate                    83.0
  total_pnl                  1847.63
  avg_pnl_per_trade            12.56
  position_size_multiplier     1.35
============================================================
```

The AI learns continuously:
- ✅ **First 10 trades**: Testing phase, baseline position size
- ✅ **After good streak**: Position size increases to 1.5x (more aggressive)
- ✅ **After losses**: Position size decreases to 0.5x (more conservative)

---

## ⚙️ 7. Adjusting AI Behavior

Want to change how the AI trades? Edit `bot.py` line 140:

```python
min_confidence = 0.45  # Lower = more trades, higher = fewer trades
```

- 🔴 0.30 → Very aggressive (many trades, more false signals)
- 🟡 0.45 → Balanced (default) - good starting point
- 🟢 0.60 → Conservative (fewer trades, higher win rate)
- 🟢 0.75 → Very conservative (only highest confidence entries)

Then restart the bot:
```bash
python bot.py
```

---

## 🧠 8. Understand AI Learning

The AI learns in 3 ways:

### 1. Initial Training (One-time)
```bash
python ai_manage.py train BTC/USDT
```
- Learns patterns from 2000 recent candles
- Identifies what price conditions lead to profitable entries
- Saved to `trading_model.h5`

### 2. Live Learning (Every trade)
```python
ai.update_from_trade(pnl=15.40, was_win=True)
```
- Bot tracks every trade outcome
- Stores win/loss ratio and total PnL
- Uses this to scale position sizes dynamically

### 3. Position Sizing (Continuous)
```
Win Rate 30% → Position size 0.5x (risky, reduce)
Win Rate 50% → Position size 1.0x (neutral)
Win Rate 70% → Position size 1.5x (profitable, increase)
```

---

## 🛠️ 9. Reset & Retrain

Start fresh with a new model:

```bash
# See current AI metrics
python ai_manage.py stats

# Delete model and metrics, start over
python ai_manage.py reset
# (Type YES when prompted)

# Retrain from scratch
python ai_manage.py train BTC/USDT
```

Reasons to reset:
- Strategy parameters changed significantly
- Model performing poorly (WR < 50%)
- Market regime changed (bull to bear)
- New trading idea to test

---

## 🚨 Troubleshooting

### "ModuleNotFoundError: No module named 'tensorflow'"

Install TensorFlow:
```bash
pip install tensorflow>=2.13.0
```

Or let pip install from requirements.txt:
```bash
pip install -r requirements.txt
```

### "AI confidence too low: 23%"

The AI model isn't confident about entries. Options:

1. **More training data**:
   ```bash
   python ai_manage.py train BTC/USDT 50  # More epochs
   ```

2. **Lower confidence threshold**:
   Edit `bot.py` line 140:
   ```python
   min_confidence = 0.30  # Was 0.45
   ```

3. **Different market conditions**:
   - Current market might not match training data
   - Try `--compare-ai` backtest to see if AI helps

### "Training accuracy too low (< 55%)"

This is normal! Market prediction is hard. Options:

1. Use a different timeframe (4h instead of 1h)
2. Train on different symbol with more trends
3. Add more features to the model (edit `ml_model.py`)

### "Bot never enters trades"

Possible reasons:

1. **No RSI signals** - Market conditions don't have oversold levels
   - Solution: Try different RSI_OVERSOLD threshold (try 40 or 45)

2. **AI always low confidence** - See "AI confidence too low" above

3. **In cooldown** - Bot is waiting after a loss
   - Reduce COOLDOWN_CANDLES in `.env` from 8 to 4

4. **Not in paper trading mode** - Check `.env`
   ```env
   PAPER_TRADING=true
   ```

---

## 📚 Advanced: Understanding the Features

The AI looks at 6 price features:

| Feature | What It Means | Example |
|---------|---------------|---------|
| **Price Change** | % change over last 20 candles | +2.5% = uptrend |
| **Volatility** | Price swing magnitude | High = risky market |
| **Momentum** | Latest candle direction | +0.5% = bullish |
| **Volume Ratio** | Current vs average volume | >1.0 = strong move |
| **RSI** | Strength of price movement | 30 = oversold (buy) |
| **Price vs 200 MA** | Trend confirmation | +2% above = uptrend |

The AI neural network learns which combinations of these features lead to profitable entries.

---

## 📈 Long-term Strategy

**Week 1-2: Learning & Backtest**
- [ ] Set up bot in paper trading
- [ ] Run backtests with and without AI
- [ ] Monitor AI statistics daily
- [ ] Build confidence in the system

**Week 3-4: Paper Trading**
- [ ] Run bot 24/7 in paper mode
- [ ] Watch for real-time trading patterns
- [ ] Let AI accumulate trade data (aim for 50+ trades)
- [ ] No interventions - let it learn

**Month 2+: Live Trading (Optional)**
- [ ] Switch `PAPER_TRADING=false` (use real money!)
- [ ] Start with small position size (TRADE_AMOUNT_USDT=10)
- [ ] Monitor live bot every day
- [ ] Scale position size gradually as confidence builds

---

## ✅ Checklist

Before going live:

- [ ] `.env` configured with API keys
- [ ] Paper trading enabled (`PAPER_TRADING=true`)
- [ ] Ran standard backtest (`python backtest.py`)
- [ ] Trained AI model (`python ai_manage.py train BTC/USDT`)
- [ ] Ran AI comparison (`python backtest.py --compare-ai`)
- [ ] AI shows improvement (PnL+ or WR+ compared to standard)
- [ ] Ran unit tests (`pytest tests/ -v`)
- [ ] Reviewed logs for errors (`tail -f bot.log`)
- [ ] Main.py set `PAPER_TRADING=true`
- [ ] Watched bot run for at least 10+ trades in paper mode

---

## 🆘 Need Help?

1. **Check logs**: `tail -f bot.log`
2. **Run tests**: `pytest tests/ -v`
3. **Review config**: `cat .env`
4. **Check AI stats**: `python ai_manage.py stats`
5. **Compare backtests**: `python backtest.py --compare-ai`

Good luck! 🚀
