# 🤖 RSI Trading Bot — Multi-pair (BTC / ETH / SOL)

A Python trading bot that uses **RSI Mean Reversion** with a **200 MA trend filter** to trade
BTC/USDT, ETH/USDT, and SOL/USDT on Binance.  
Comes with a **backtester**, paper-trading mode, trailing stop, and per-trade cooldown after losses.

---

## 🧠 Strategy

| Signal | Condition |
|--------|-----------|
| **BUY**  | Price is **above** the 200-candle MA (uptrend confirmed) **and** RSI crosses **below** the oversold threshold (default 35) |
| **EXIT** | Trailing stop (−2.5%) or take-profit (+8%) — no RSI-based sell |

Additional protection: initial stop-loss of −3% on entry, cooldown of 8 candles after a losing trade.

---

## 🚀 Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure the bot
Edit `config.py` and fill in your settings:
```python
API_KEY    = "YOUR_BINANCE_API_KEY"
API_SECRET = "YOUR_BINANCE_API_SECRET"
SYMBOLS    = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
TIMEFRAME  = "1h"
PAPER_TRADING = True   # ← Always test first!
```

### 3. Run the backtester first
Always backtest before going live:
```bash
python backtest.py
```

### 4. Run the bot (paper trading)
```bash
python bot.py
```

---

## 📁 File Structure

```
trading-bot/
├── bot.py           # Main bot loop
├── strategy.py      # RSI + 200 MA signal logic
├── backtest.py      # Historical backtest
├── config.py        # Your settings & API keys  ← NOT pushed to GitHub
├── requirements.txt
└── README.md
```

---

## ⚠️ Disclaimer

This bot is for **educational purposes**. Crypto trading carries significant risk.
Always test in paper mode first. Never trade money you can't afford to lose.

---

## 📤 Push to GitHub

```bash
# 1. Create a new repo on github.com, then:
git init
git add .
git commit -m "Initial trading bot"
git remote add origin https://github.com/YOUR_USERNAME/trading-bot.git
git push -u origin main
```

> ⚠️ `config.py` is in `.gitignore` — your API keys will NOT be pushed.
> Share a `config.example.py` instead if collaborating.

---

## ⚙️ Tuning Tips

- Try **RSI period 7–21** — shorter = more signals, noisier
- Try **4h or 1d timeframe** for fewer but cleaner signals
- Increase `TAKE_PROFIT_PCT` if your win rate is high
- Adjust `COOLDOWN_CANDLES` to limit re-entries after losses
- Always re-run `backtest.py` after changing settings
