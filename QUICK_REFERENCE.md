# 🚀 QUICK REFERENCE CARD

**Trading Bot Phase 6 - All Essential Commands**

---

## 🎯 FIRST TIME SETUP

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Interactive configuration
python setup.py

# 3. Verify setup
python cli.py validate-config
```

---

## ▶️ RUN THE BOT

```bash
# Start stock bot with Discord + retraining
python stock_bot.py

# Start crypto bot (Binance)
python bot.py

# Use launcher script (interactive menu)
./launch.sh
```

---

## 📊 VIEW PERFORMANCE

```bash
# Dashboard (performance stats)
python dashboard.py

# Live logs
tail -f stock_bot.log

# AI statistics
python cli.py stats
```

---

## 🛠️ MANAGEMENT COMMANDS

```bash
# Validate configuration
python cli.py validate-config

# Test Discord webhook
python cli.py test-discord

# Force AI model retraining
python cli.py retrain

# Detailed trade analysis
python cli.py analyze

# ⚠️ Clear all trade history
python cli.py reset-trades

# Show version
python cli.py version
```

---

## 💾 CONFIGURATION (.env)

### Required
```ini
ALPACA_API_KEY=PK_...
ALPACA_API_SECRET=secret
```

### Recommended
```ini
MIN_AI_CONFIDENCE=0.45        # AI confidence threshold
MAX_DAILY_LOSS_PCT=5          # Max daily loss
MAX_OPEN_POSITIONS=2          # Max concurrent trades
MIN_TRADE_USDT=10             # Minimum trade size
```

### Optional (Discord)
```ini
DISCORD_WEBHOOK_URL=https://discordapp.com/api/webhooks/...
```

---

## 📁 KEY FILES

| File | Purpose |
|------|---------|
| stock_bot.py | Main bot - run this |
| dashboard.py | Performance monitor |
| cli.py | Management commands |
| GUIDE_PHASE6.md | Complete documentation |
| trades_history.csv | Auto-generated trade log |
| stock_bot.log | Auto-generated logs |

---

## 🔄 AUTOMATIC FEATURES

| Feature | Trigger | Output |
|---------|---------|--------|
| Trade Logging | Every trade | trades_history.csv |
| Discord Alert | Every trade | Discord message |
| Model Retraining | Every 20 trades | trading_model_rf.pkl |
| Performance Summary | On demand | dashboard.py |

---

## 📈 WHAT TO EXPECT

- **Win Rate**: 55-65% (realistic)
- **Monthly Returns**: +5-15% (good)
- **Trades/Day**: 5-15 (depends on market)
- **Drawdowns**: 5-10% (normal)

---

## 🐛 QUICK TROUBLESHOOTING

| Issue | Fix |
|-------|-----|
| No API key error | Run `python setup.py` |
| Discord not working | Check DISCORD_WEBHOOK_URL |
| No trades | Let bot run 30-60 mins |
| Model not retraining | Need ≥20 closed trades |
| Configuration error | Run `python cli.py validate-config` |

---

## 📞 GET HELP

```bash
# See full documentation
cat GUIDE_PHASE6.md

# Validate everything
python cli.py validate-config

# Review logs
tail -f stock_bot.log

# Check stats
python cli.py stats
```

---

## 🎬 COMPLETE STARTUP (5 STEPS)

```bash
# Step 1: Setup (first time only)
python setup.py

# Step 2: Verify
python cli.py validate-config

# Step 3: Terminal 1 - Run bot
python stock_bot.py

# Step 4: Terminal 2 - View dashboard
python dashboard.py

# Step 5: Watch Discord channel (if configured)
# Messages appear automatically on every trade
```

---

**Ready? Start with**: `python setup.py`

**Then**: `python stock_bot.py`

**Monitor**: `python dashboard.py`

---

*Detailed docs: See GUIDE_PHASE6.md or PHASE6_SUMMARY.md*
