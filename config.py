API_KEY    = "YOUR_BINANCE_API_KEY"
API_SECRET = "YOUR_BINANCE_API_SECRET"

# --- Multi-pair trading ---
SYMBOLS    = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
TIMEFRAME  = "1h"

# RSI Settings
RSI_PERIOD     = 10
RSI_OVERSOLD   = 35
RSI_OVERBOUGHT = 70

# Risk Management — per trade
TRADE_AMOUNT_USDT  = 20.0
TRAILING_STOP_PCT  = 0.025
COOLDOWN_CANDLES   = 8        # wait 8 candles (~8h) after a loss before re-entering
STOP_LOSS_PCT      = 0.03
TAKE_PROFIT_PCT    = 0.08

PAPER_TRADING  = True
CHECK_INTERVAL = 60
