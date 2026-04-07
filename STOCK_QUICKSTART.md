# 📈 Stock Trading Bot Setup Guide

## ⚡ Quick Start (5 Minutes)

### 1. Get Free Alpaca API Keys (2 min)

Go to: https://app.alpaca.markets

1. Click **Sign up** (free)
2. Fill in details (name, email, password)
3. Verify email
4. Go to **Account Settings** → **API Keys**
5. Copy **API Key** and **Secret Key**

> ✅ Alpaca gives you **$100,000 paper trading** for free!

### 2. Update `.env` File (2 min)

Add these lines to your `.env` (keep your existing Bitcoin settings):

```env
# Alpaca Stock Trading (Paper Mode)
ALPACA_API_KEY=PK123...your_api_key_here
ALPACA_API_SECRET=abc123...your_secret_key_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# What stocks to trade (SPY, QQQ, VOO by default)
STOCK_SYMBOLS=SPY,QQQ,VOO
STOCK_TIMEFRAME=1h

# RSI Settings (adjusted for stocks)
STOCK_RSI_PERIOD=14
STOCK_RSI_OVERSOLD=35
STOCK_RSI_OVERBOUGHT=65

# Position Size: $20 per trade
STOCK_TRADE_AMOUNT=20.0

# Risk Management
STOCK_STOP_LOSS=0.03        # 3% stop loss
STOCK_TAKE_PROFIT=0.05      # 5% profit target
STOCK_TRAILING_STOP=0.02    # 2% trailing stop
STOCK_COOLDOWN=4            # 4 bars after loss

# Trading Mode
STOCK_PAPER_TRADING=true    # ALWAYS true unless you're advanced!
STOCK_CHECK_INTERVAL=60     # Check every 60 seconds
STOCK_LOG_LEVEL=INFO

# Use AI to improve entries?
STOCK_USE_AI=true
```

### 3. Install Dependencies (1 min)

```bash
pip install -r requirements.txt
```

### 4. Run the Bot! (1 min)

```bash
python stock_bot.py
```

Expected output:
```
2026-04-07 14:23:45  INFO      ✅ Connected to Alpaca (PAPER TRADING)
2026-04-07 14:23:46  INFO      🤖 Stock Bot started | Symbols: ['SPY', 'QQQ', 'VOO'] | 1h
2026-04-07 14:23:46  INFO      🧠 AI active | Trades: 0 | WR: 0%
2026-04-07 14:24:15  INFO      [SPY] price=$450.25  
2026-04-07 14:25:30  INFO      [QQQ] BUY signal | AI: 58%
2026-04-07 14:25:31  INFO      [PAPER] BUY 1 QQQ
```

---

## 🎯 What the Bot Does

### Strategy: RSI Mean Reversion (Same as Crypto)

| Signal | Meaning |
|--------|---------|
| **BUY** | RSI < 35 (oversold) + price above 200 MA (uptrend) + AI confirms |
| **EXIT** | Trailing stop (2%) or take profit (5%) |

### Features

- ✅ **RSI-based entries** - Buys oversold conditions
- ✅ **200 MA filter** - Only buys in uptrends
- ✅ **AI predictions** - Improves entry quality
- ✅ **Position sizing** - $20 per trade (safe amount)
- ✅ **Trailing stops** - Locks in profits
- ✅ **Paper trading** - No real money at risk
- ✅ **Real market hours** - 9:30 AM - 4:00 PM EST (Mon-Fri)

---

## 📊 Example: First Trade

```
[SPY] RSI drops below 35 during uptrend
     ↓
[AI] Predicts 62% chance of success
     ↓
[BOT] Enters: BUY 1 SPY @ $450.25
     ↓
[Monitor] Trailing stop at $441.25, target at $472.76
     ↓
[SPY] Price rises to $472
     ↓
[BOT] EXIT TAKE_PROFIT @ $472.76
     ↓
[AI] Updates: +$22.51 gain, win rate now 100%
```

---

## 🧠 Using AI with Stocks

The same AI model learns from stock trades too!

### Check AI Performance

```bash
python ai_manage.py stats
```

### Train on Stock Data (Optional)

```bash
# Train AI specifically on stock market
python ai_manage.py train SPY 20
```

---

## ⏰ Important: Trading Hours

Alpaca paper trading works during **US market hours**:

- **Monday - Friday**: 9:30 AM - 4:00 PM EST
- **Before/After hours**: No trading available in paper mode
- **Weekends**: Market closed

👉 **Start the bot during market hours!**

---

## 📈 Recommended Stocks

| Ticker | Type | Volatility | Notes |
|--------|------|-----------|-------|
| **SPY** | S&P 500 ETF | Medium | Most stable, best for beginners |
| **QQQ** | Nasdaq 100 ETF | High | Tech stocks, more swings |
| **VOO** | S&P 500 ETF | Medium | Similar to SPY, low fees |
| **IVV** | S&P 500 ETF | Medium | Alternative to SPY |
| **AAPL** | Apple stock | Medium | Individual stock example |

For beginners: **Start with SPY (most stable)**

---

## 🎮 Commands

### Start Trading
```bash
python stock_bot.py
```

### Check AI Stats
```bash
python ai_manage.py stats
```

### Test Strategy (Backtest)
```bash
# Backtest standard RSI strategy
python backtest.py

# Backtest with AI
python backtest.py --compare-ai
```

### View Logs
```bash
tail -f stock_bot.log
```

---

## ⚠️ Safety First

| Rule | Reason |
|------|--------|
| **Paper trading only** | No real money at risk |
| **Small position size** | $20 = ~1 share, small losses |
| **Don't go live yet** | Learn first, trade later |
| **Monitor first 10 trades** | Make sure system works |
| **No overnight positions** | Market closes 4 PM, reopens 9:30 AM |

---

## 🚨 Troubleshooting

### "Authentication failed"
- Double-check API key and secret in `.env`
- Make sure you're using **Paper trading key** (not live!)
- Restart bot: `python stock_bot.py`

### "Insufficient data"
- Stock just started trading
- Try different stock symbol
- Wait for more historical data

### "Market is closed"
- Check time: 9:30 AM - 4:00 PM EST, Mon-Fri only
- Wait until market opens
- Weekend/holiday? Market is closed!

### "No trades happening"
- Check RSI is actually < 35 during uptrend
- Maybe market is trending down → no buys
- Check bot log: `tail -f stock_bot.log`

---

## 💡 Advanced: Changing Settings

Want more/fewer trades? Edit `.env`:

```env
# More aggressive (more trades)
STOCK_RSI_OVERSOLD=40          # Buy at RSI 40 instead of 35
STOCK_TAKE_PROFIT=0.03         # Accept 3% profit instead of 5%

# More conservative (fewer trades, higher win rate)
STOCK_RSI_OVERSOLD=30          # Only buy at RSI < 30
STOCK_TAKE_PROFIT=0.10         # Wait for 10% profit
```

Then restart bot and backtest new settings:
```bash
python backtest.py --compare-ai
```

---

## 🎓 Learning Path

### Week 1: Paper Trading
```bash
# Day 1-3: Run bot, watch trades
python stock_bot.py

# Day 4-7: Monitor 20+ trades, check AI stats
python ai_manage.py stats
```

### Week 2: Optimization
```bash
# Backtest different settings
python backtest.py --compare-ai

# Maybe adjust RSI_OVERSOLD or TAKE_PROFIT
```

### Week 3+: Decide
- ✅ System profitable? → Consider live trading ($1 positions!)
- ❌ System not working? → Adjust settings, retrain AI
- ❓ Not sure? → Keep trading paper mode

---

## 📞 Support

1. **Check logs**: `tail -f stock_bot.log`
2. **Validate config**: Check `.env` file
3. **Test connection**: `python -c "import alpaca_trade_api; print('OK')"`
4. **Run tests**: `pytest tests/ -v`

---

## 🎯 Your First Command

```bash
# This is it! One command and you're trading:
python stock_bot.py
```

That's it! The bot will:
- Connect to Alpaca
- Watch SPY, QQQ, VOO
- Buy when RSI dips + AI agrees
- Manage trades with stops
- Learn from outcomes

**Good luck! 📈**
