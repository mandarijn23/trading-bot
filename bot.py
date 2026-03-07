"""
Main Trading Bot
-----------------
Connects to Binance, polls for new candles on the configured
interval, evaluates the RSI strategy, and places trades.

Run:  python bot.py
"""

import time
import logging
from datetime import datetime

import ccxt
import pandas as pd

import config
from strategy import get_signal

# ── Logging setup ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


# ── Exchange connection ────────────────────────────────────────
def connect() -> ccxt.binance:
    exchange = ccxt.binance({
        "apiKey":  config.API_KEY,
        "secret":  config.API_SECRET,
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    })
    if config.PAPER_TRADING:
        log.info("🟡  PAPER TRADING MODE – no real orders will be placed")
    else:
        log.warning("🔴  LIVE TRADING MODE – real money at risk!")
    return exchange


# ── Market data ────────────────────────────────────────────────
def fetch_ohlcv(exchange: ccxt.binance, symbol: str, timeframe: str, limit: int = 100) -> pd.DataFrame:
    raw = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df  = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


# ── Order helpers ──────────────────────────────────────────────
def get_balance(exchange: ccxt.binance, currency: str = "USDT") -> float:
    balance = exchange.fetch_balance()
    return balance["free"].get(currency, 0.0)


def place_order(exchange: ccxt.binance, side: str, symbol: str, usdt_amount: float, price: float):
    qty = round(usdt_amount / price, 6)

    if config.PAPER_TRADING:
        log.info(f"[PAPER] {side.upper()} {qty} {symbol} @ {price:.2f} USDT")
        return {"id": "PAPER", "side": side, "amount": qty, "price": price}

    try:
        order = exchange.create_market_order(symbol, side, qty)
        log.info(f"✅ {side.upper()} order placed: {order}")
        return order
    except ccxt.BaseError as e:
        log.error(f"Order failed: {e}")
        return None


# ── Position tracker (in-memory) ──────────────────────────────
class Position:
    def __init__(self):
        self.active      = False
        self.entry_price = 0.0
        self.qty         = 0.0
        self.stop_loss   = 0.0
        self.take_profit = 0.0

    def open(self, price: float, qty: float):
        self.active      = True
        self.entry_price = price
        self.qty         = qty
        self.stop_loss   = price * (1 - config.STOP_LOSS_PCT)
        self.take_profit = price * (1 + config.TAKE_PROFIT_PCT)
        log.info(f"📈 Position opened | entry={price:.2f}  SL={self.stop_loss:.2f}  TP={self.take_profit:.2f}")

    def close(self):
        self.active = False
        log.info("📉 Position closed")

    def check_exit(self, current_price: float) -> str:
        """Returns 'STOP_LOSS', 'TAKE_PROFIT', or 'HOLD'."""
        if not self.active:
            return "HOLD"
        if current_price <= self.stop_loss:
            return "STOP_LOSS"
        if current_price >= self.take_profit:
            return "TAKE_PROFIT"
        return "HOLD"


# ── Main loop ──────────────────────────────────────────────────
def run():
    exchange = connect()
    position = Position()
    log.info(f"🤖 Bot started | {config.SYMBOL} | {config.TIMEFRAME} | RSI({config.RSI_PERIOD})")

    while True:
        try:
            df    = fetch_ohlcv(exchange, config.SYMBOL, config.TIMEFRAME)
            price = df["close"].iloc[-1]

            # ── Check exit conditions first ──
            exit_reason = position.check_exit(price)
            if exit_reason in ("STOP_LOSS", "TAKE_PROFIT"):
                log.info(f"🚨 Exiting: {exit_reason} triggered at {price:.2f}")
                place_order(exchange, "sell", config.SYMBOL, config.TRADE_AMOUNT_USDT, price)
                position.close()

            # ── Evaluate entry signal ──
            elif not position.active:
                signal = get_signal(df, config.RSI_PERIOD, config.RSI_OVERSOLD, config.RSI_OVERBOUGHT)
                log.info(f"Price={price:.2f}  Signal={signal}")

                if signal == "BUY":
                    order = place_order(exchange, "buy", config.SYMBOL, config.TRADE_AMOUNT_USDT, price)
                    if order:
                        qty = config.TRADE_AMOUNT_USDT / price
                        position.open(price, qty)

            else:
                log.info(f"Price={price:.2f}  Holding position (entry={position.entry_price:.2f})")

        except ccxt.NetworkError as e:
            log.warning(f"Network error, retrying… {e}")
        except ccxt.ExchangeError as e:
            log.error(f"Exchange error: {e}")
        except KeyboardInterrupt:
            log.info("Bot stopped by user.")
            break
        except Exception as e:
            log.error(f"Unexpected error: {e}", exc_info=True)

        time.sleep(config.CHECK_INTERVAL)


if __name__ == "__main__":
    run()
