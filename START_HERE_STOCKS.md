# 🚀 Quick Start: Stocks vs Crypto Comparison

## Which Bot Should I Use?

### 🪙 Crypto Bot (Bitcoin, Ethereum, etc)
```bash
python bot.py
```
- **Asset**: BTC, ETH, SOL
- **Exchange**: Binance (real money or paper)
- **Hours**: 24/7 trading
- **Setup**: Add API keys to `.env`
- **Risk**: Paper or live mode

### 📈 Stock Bot (SPY, QQQ, VOO)
```bash
python stock_bot.py
```
- **Asset**: US stocks & ETFs
- **Exchange**: Alpaca (paper trading FREE)
- **Hours**: 9:30 AM - 4:00 PM EST (Mon-Fri)
- **Setup**: 3-minute setup
- **Risk**: Paper only (no real money needed!)

---

## 🎯 I Want: Stock Trading (Right Now!)

### Step 1: Auto Setup (Recommended - 2 minutes)
```bash
python setup_stocks.py
```

This will:
1. Ask for Alpaca API keys (free!)
2. Configure your `.env` file
3. Test connection
4. Install dependencies

### Step 2: Start Trading
```bash
python stock_bot.py
```

The bot will immediately start trading **SPY, QQQ, VOO** in paper mode.

### Step 3: Monitor (Another terminal)
```bash
# Watch live trading
tail -f stock_bot.log

# Check AI stats
python ai_manage.py stats
```

---

## 📋 Complete Setup Path (Manual)

### 1. Get Alpaca API Keys (3 min)
- Go to: https://app.alpaca.markets
- Sign up (free)
- Verify email  
- Settings → API Keys
- Copy key and secret

### 2. Add to `.env` (1 min)
```bash
nano .env
```

Add these lines:
```env
ALPACA_API_KEY=your_key_here
ALPACA_API_SECRET=your_secret_here
STOCK_USE_AI=true
STOCK_PAPER_TRADING=true
```

### 3. Install (1 min)
```bash
pip install -r requirements.txt
```

### 4. Validate (1 min)
```bash
python validate_setup.py
```

### 5. Trade (Now!)
```bash
python stock_bot.py
```

---

## 🧠 Both Bots With AI?

✅ **YES!** Both bots use the same AI system:

- **Crypto Bot** (bitcoin): Uses AI to predict crypto entry points
- **Stock Bot** (stocks): Uses same AI to predict stock entry points

The AI **learns from both**! 

Check combined performance:
```bash
python ai_manage.py stats
```

---

## 📊 Example Trade Sequence (Stocks)

```
[9:35 AM] Market opens, bot starts
[10:15] SPY RSI drops to 32 (oversold signal)
[10:16] AI predicts 71% chance of success
[10:16] 🤖 BOT BUYS: 1 SPY @ $450.25
[10:17] Set trailing stop @ $441.25, target @ $472.76
[10:45] SPY rises to $472
[10:46] 🤖 BOT EXITS: TAKE_PROFIT @ $472.76
[10:47] 💰 Win: +$22.51 (5% gain)
[10:47] 🧠 AI learns: Position size now 1.1x (profitable, slightly increase)
```

---

## 🔄 Commands Cheat Sheet

### Trading
```bash
python stock_bot.py          # Start stock trading
python bot.py                # Start crypto trading
python backtest.py --compare-ai  # Test strategy
```

### AI Management
```bash
python ai_manage.py stats           # Show performance
python ai_manage.py train SPY 20    # Train on stock data
python ai_manage.py reset           # Start fresh
```

### Setup & Validation
```bash
python setup_stocks.py              # Interactive setup
python validate_setup.py            # Check everything
```

### Monitoring
```bash
tail -f stock_bot.log               # Watch live logs
tail -f bot.log                     # Crypto bot logs
grep "BUY\|TAKE_PROFIT" stock_bot.log  # Recent trades
```

### Tests
```bash
pytest tests/ -v                    # Run all tests
pytest tests/test_ml_model.py -v   # Test AI
pytest tests/test_config.py -v     # Test config
```

---

## ⚡ TL;DR (30 seconds)

```bash
# 1. Setup
python setup_stocks.py

# 2. Trade
python stock_bot.py

# Done! 🎉
```

That's it! The bot handles the rest.

---

## ❓ FAQs

**Q: Do I need real money?**
A: No! Paper trading is free. You get $100,000 virtual balance. ✅

**Q: When can I trade stocks?**
A: Only market hours: 9:30 AM - 4:00 PM EST, Monday-Friday.

**Q: What if I make mistakes?**
A: Paper trading = no real money at risk. Experiment freely!

**Q: Can AI trade for me?**
A: Yes! AI filters entries, manages position sizes, learns from trades.

**Q: Can I trade real money?**
A: Yes, but start with paper trading first. After 50+ paper trades, consider $1 amounts.

**Q: Do I need to code?**
A: No! Just run `python stock_bot.py`. It does everything.

---

## 📚 Documentation

| File | Purpose |
|------|---------|
| **STOCK_README.md** | Quick overview (read first!) |
| **STOCK_QUICKSTART.md** | Detailed setup guide |
| **AI_QUICKSTART.md** | How AI learns & works |
| **README.md** | Original crypto bot docs |

---

## 🎯 Your Next Action

**Try stock trading right now:**

```bash
python setup_stocks.py
```

Takes 3 minutes, then you're trading! 🚀

---

## 🆘 Need Help?

1. Read: **STOCK_README.md** or **STOCK_QUICKSTART.md**
2. Check: `python validate_setup.py`
3. Logs: `tail -f stock_bot.log`
4. Test: `python backtest.py --compare-ai`

---

**Ready to trade stocks? Run this now:**

```bash
python setup_stocks.py && python stock_bot.py
```

🎉 Let's make some pips!
