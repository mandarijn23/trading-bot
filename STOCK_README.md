# 📈 Stock Trading Bot — 3-Minute Quick Start

## One Command to Trade Real Stocks

```bash
python stock_bot.py
```

That's it! The bot will trade **SPY, QQQ, VOO** with $20 per trade in paper mode.

---

## 🚀 Setup (3 minutes for first-timers)

### Option A: Interactive Setup (Recommended)

```bash
python setup_stocks.py
```

This will:
1. Ask for your Alpaca API keys
2. Create `.env` file
3. Test connection
4. You're ready!

### Option B: Manual Setup

1. Create Alpaca account: https://app.alpaca.markets
2. Get API keys from Account Settings
3. Add to `.env`:
   ```env
   ALPACA_API_KEY=your_key_here
   ALPACA_API_SECRET=your_secret_here
   STOCK_USE_AI=true
   STOCK_PAPER_TRADING=true
   ```
4. Run bot: `python stock_bot.py`

---

## 📊 What the Bot Does

- 📈 Watches **SPY, QQQ, VOO** (S&P 500 ETFs)
- 🎯 Buys when **RSI < 35** (oversold) + uptrend
- 🤖 Uses **AI to filter entries** (improves accuracy)
- 💰 **$20 per trade** (small, safe amount)
- 🛑 **Exits with trailing stops** (locks profits)
- 🧠 **Learns from trades** (improves over time)

---

## ⏰ Important: Market Hours Only

Trading only works during US market hours:
- **9:30 AM - 4:00 PM EST**, Monday-Friday
- Not weekends or holidays

Start the bot during market hours!

---

## 🎮 First Run Example

```bash
$ python stock_bot.py

2026-04-07 10:30:15  INFO  ✅ Connected to Alpaca (PAPER TRADING)
2026-04-07 10:30:16  INFO  🤖 Stock Bot started | Symbols: ['SPY', 'QQQ', 'VOO'] | 1h
2026-04-07 10:30:16  INFO  🧠 AI active | Trades: 0 | WR: 0%
2026-04-07 10:31:00  INFO  [SPY] $450.25  
2026-04-07 10:32:00  INFO  [QQQ] BUY signal | AI: 62%
2026-04-07 10:32:01  INFO  [PAPER] BUY 1 QQQ
2026-04-07 11:00:00  INFO  [QQQ] EXIT TAKE_PROFIT @ $472.50
2026-04-07 11:00:00  INFO  🤖 AI Updated: 1 trades, WR=100.0%, PnL=$22.50
```

---

## � Discord Real-Time Alerts (Optional)

Get live notifications for every trade! 📱

**Setup (2 minutes):**

```bash
# 1. Create Discord webhook (see DISCORD_SETUP.md)
# 2. Add to .env:
DISCORD_WEBHOOK_URL=https://discordapp.com/api/webhooks/YOUR_ID/YOUR_TOKEN

# 3. Test:
python cli.py test-discord
```

**See alerts for:**
- 🟢 Every BUY with entry price, quantity, AI confidence
- 🔴 Every SELL with profit/loss and exit reason
- 📊 Daily summary with trade count and win rate

👉 **[Full Discord setup guide →](DISCORD_SETUP.md)**

---

## �📁 File Structure

```
trading-bot/
├── stock_bot.py           ← Run this! (python stock_bot.py)
├── stock_config.py        ← Stock configuration
├── setup_stocks.py        ← Setup helper
├── STOCK_QUICKSTART.md    ← Full guide
├── .env                   ← Your API keys (auto-created)
└── stock_bot.log          ← Trading logs
```

---

## 🧠 AI Learning

The AI model improves over time:

**After 5 trades:** Win rate 80%
```
[BOT] Position size × 1.0 (neutral)
```

**After 20 trades:** Win rate 70%
```
[BOT] Position size × 1.3 (profitable, increase!)
```

**After 50 trades losing streak:** Win rate 40%
```
[BOT] Position size × 0.6 (protect capital, decrease!)
```

Check AI stats anytime:
```bash
python ai_manage.py stats
```

---

## 🔄 Common Commands

| Command | Purpose |
|---------|---------|
| `python stock_bot.py` | Start trading |
| `python ai_manage.py stats` | Check AI performance |
| `tail -f stock_bot.log` | Watch live logs |
| `python setup_stocks.py` | Reconfigure API keys |
| `python backtest.py --compare-ai` | Test strategy |

---

## ⚠️ Safety Rules

✅ **DO:**
- Start in paper trading (no real money)
- Use small amounts ($10-50 per trade)
- Monitor first 20 trades
- Keep API key secret!

❌ **DON'T:**
- Go live trading immediately
- Use all your money
- Leave bot unattended for hours
- Share your API keys

---

## 🚨 Troubleshooting

### "Authentication failed"
→ Check API key and secret in `.env`

### "Market is closed"  
→ Only 9:30 AM - 4:00 PM EST, Mon-Fri

### "No trades"
→ Maybe market is trending down (no buys)
→ Check logs: `tail -f stock_bot.log`

### "Connection error"
→ Run: `python setup_stocks.py` to test

---

## 📚 Learn More

- **STOCK_QUICKSTART.md** — Full setup guide
- **AI_QUICKSTART.md** — How AI works
- **README.md** — General bot documentation

---

## 🎯 Next Steps

1. **Run setup**: `python setup_stocks.py` (or manual .env)
2. **Start trading**: `python stock_bot.py`
3. **Monitor**: Watch logs during market hours
4. **Check stats**: `python ai_manage.py stats` after 10+ trades
5. **Optimize**: Adjust RSI_OVERSOLD and TAKE_PROFIT if desired
6. **Feel confident**: After 50+ paper trades, consider live trading with $1 amounts

---

**You're ready! Run this now:**

```bash
python stock_bot.py
```

🚀 Happy trading!
