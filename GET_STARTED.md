# 🚀 Get Started with Trading Bot

Your trading bot is ready! Choose your path below:

---

## ⚡ Quick Start (Pick One)

### 📈 **I want to trade STOCKS** (Recommended for beginners)

```bash
# Step 1: One-time setup (2 minutes)
python setup_stocks.py

# Step 2: Start trading!
python stock_bot.py
```

**What you get:**
- 🎯 Trade real stocks (SPY, QQQ, VOO)
- 📱 Paper trading ($100k virtual money)
- 🤖 AI learns from every trade
- ✅ 9:30 AM - 4:00 PM EST trading
- 💰 NO REAL MONEY AT RISK

---

### 🪙 **I want to trade CRYPTO** (Advanced)

```bash
# Add your Binance API keys to .env file first

# Then run:
python bot.py
```

**What you get:**
- 🎯 Trade crypto 24/7
- 🤖 AI adapts to market conditions
- 📊 BTC, ETH, SOL on Binance
- ⚙️ Full control over settings

---

### 🧪 **I want to test before trading**

```bash
# Backtest the strategy on historical data
python backtest.py

# Compare vs AI-enhanced version
python backtest.py --compare-ai

# See side-by-side comparison
python backtest.py --ai-enhanced
```

---

## 🎮 Interactive Menu

Don't want to remember commands? Just run:

```bash
python trade.py
```

Then choose what you want from the menu!

---

## 📚 Detailed Guides

### Stock Trading
- [STOCK_QUICKSTART.md](STOCK_QUICKSTART.md) - Step-by-step setup
- [STOCK_README.md](STOCK_README.md) - Commands & FAQ
- [START_HERE_STOCKS.md](START_HERE_STOCKS.md) - Crypto vs Stocks

### AI System
- [AI_QUICKSTART.md](AI_QUICKSTART.md) - How the AI works
- `python ai_manage.py stats` - Check performance
- `python ai_manage.py train` - Retrain model

### Original README
- [README.md](README.md) - Project overview

---

## 🛠️ Tools

| Command | What it does |
|---------|------------|
| `python trade.py` | Interactive menu (easiest) |
| `python stock_bot.py` | Start stock trading bot |
| `python bot.py` | Start crypto trading bot |
| `python setup_stocks.py` | Configure Alpaca API keys |
| `python validate_setup.py` | Check everything is working |
| `python backtest.py` | Test strategy historically |
| `python ai_manage.py stats` | See AI performance |

---

## ✅ Checklist Before Starting

### For Stock Trading
- [ ] Run `python setup_stocks.py` first
- [ ] Verify .env file has `ALPACA_API_KEY` and `ALPACA_API_SECRET`
- [ ] Run `python validate_setup.py` to test
- [ ] Check balance appears correctly

### For Crypto Trading
- [ ] Add `BINANCE_API_KEY` to .env
- [ ] Add `BINANCE_API_SECRET` to .env
- [ ] Set trading pair in config.py
- [ ] Decide paper or live mode

---

## 🤖 How AI Works

The bot has a smart AI that:

1. **Learns from history** - Studies past market data
2. **Makes predictions** - Decides entry confidence (0-100%)
3. **Adapts position size** - Bigger bets when confident, smaller when uncertain
4. **Learns from trades** - Gets smarter after each win/loss
5. **Stays disciplined** - Always respects stop losses and profit targets

---

## 💰 Risk Management

Built-in protections:

| Feature | Default |
|---------|---------|
| Stop loss | 2% below entry |
| Profit target | 3% above entry |
| Max position | $20 per trade (stocks) |
| Cooldown | Skip after loss |
| Max daily trades | ~5-10 per symbol |

---

## 🚨 Common Issues

### "API key not found"
```bash
# Add your keys to .env file:
echo "ALPACA_API_KEY=pk_..." >> .env
echo "ALPACA_API_SECRET=..." >> .env
```

### "Can't connect to Alpaca"
```bash
# Validate your setup:
python validate_setup.py
```

### "No trades happening"
```bash
# Check strategy signals:
python backtest.py

# Check AI stats:
python ai_manage.py stats
```

### "ModuleNotFoundError"
```bash
# Install dependencies:
pip install -r requirements.txt
```

---

## 📞 Need Help?

1. **For stock setup:** See [STOCK_QUICKSTART.md](STOCK_QUICKSTART.md)
2. **For AI questions:** See [AI_QUICKSTART.md](AI_QUICKSTART.md)
3. **For general info:** See [START_HERE_STOCKS.md](START_HERE_STOCKS.md)
4. **For errors:** Run `python validate_setup.py`

---

## ✨ That's it!

You're ready to go. Pick your asset class and run:

```bash
python trade.py
```

Happy trading! 🚀
