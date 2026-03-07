# 🤖 RSI Trading Bot — Binance / BTC

A Python trading bot that uses **RSI Mean Reversion** to trade BTC/USDT on Binance.
Comes with a **backtester**, paper trading mode, and stop-loss / take-profit management.

---

## 🧠 Strategy

| Signal | Condition |
|--------|-----------|
| **BUY**  | RSI crosses **below** 30 (oversold — price likely to bounce) |
| **SELL** | RSI crosses **above** 70 (overbought — price likely to pull back) |

Additional exits: Stop-loss (−3%) and Take-profit (+6%) to protect capital.

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
SYMBOL     = "BTC/USDT"
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
├── strategy.py      # RSI signal logic
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
- Always re-run `backtest.py` after changing settings
