# ─────────────────────────────────────────────
#  TRADING BOT CONFIG
#  Copy this file and fill in your API keys.
#  Never commit real keys to GitHub!
# ─────────────────────────────────────────────

# --- Binance API (get from binance.com > API Management) ---
API_KEY    = "YOUR_BINANCE_API_KEY"
API_SECRET = "YOUR_BINANCE_API_SECRET"

# --- Trading Pair & Timeframe ---
SYMBOL     = "BTC/USDT"   # Any pair available on Binance
TIMEFRAME  = "1h"         # 1m, 5m, 15m, 1h, 4h, 1d

# --- RSI Strategy Settings ---
RSI_PERIOD     = 14    # Standard RSI look-back period
RSI_OVERSOLD   = 30    # Buy signal when RSI drops below this
RSI_OVERBOUGHT = 70    # Sell signal when RSI rises above this

# --- Risk Management ---
TRADE_AMOUNT_USDT = 20.0   # Amount in USDT per trade
STOP_LOSS_PCT     = 0.03   # 3% stop loss
TAKE_PROFIT_PCT   = 0.06   # 6% take profit (2:1 reward/risk)

# --- Mode ---
# Set PAPER_TRADING = True to simulate without real money
PAPER_TRADING = True

# --- Loop interval (seconds between each check) ---
CHECK_INTERVAL = 60
