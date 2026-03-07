"""
Multi-pair Trading Bot — RSI + 200 MA + Trailing Stop
-------------------------------------------------------
Trades BTC, ETH, and SOL simultaneously.
Run:  python bot.py
"""

import time
import logging
import ccxt
import pandas as pd

import config
from strategy import get_signal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


def connect():
    if config.PAPER_TRADING:
        # No API key needed for paper trading — uses public market data only
        exchange = ccxt.binance({"enableRateLimit": True})
        log.info("[PAPER] TRADING MODE — no API key required")
    else:
        exchange = ccxt.binance({
            "apiKey":  config.API_KEY,
            "secret":  config.API_SECRET,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })
        log.info("[LIVE] TRADING MODE — real money at risk!")
    return exchange


def fetch_ohlcv(exchange, symbol, limit=250):
    raw = exchange.fetch_ohlcv(symbol, config.TIMEFRAME, limit=limit)
    df  = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def place_order(exchange, side, symbol, price):
    qty = round(config.TRADE_AMOUNT_USDT / price, 6)
    if config.PAPER_TRADING:
        log.info(f"[PAPER] {side.upper()} {qty} {symbol} @ {price:.2f}")
        return True
    try:
        exchange.create_market_order(symbol, side, qty)
        return True
    except ccxt.BaseError as e:
        log.error(f"Order failed ({symbol}): {e}")
        return False


class Position:
    def __init__(self, symbol):
        self.symbol        = symbol
        self.active        = False
        self.entry_price   = 0.0
        self.peak_price    = 0.0
        self.trailing_stop = 0.0
        self.take_profit   = 0.0
        self.cooldown      = 0      # intervals to wait before next entry

    def open(self, price):
        self.active        = True
        self.entry_price   = price
        self.peak_price    = price
        self.trailing_stop = price * (1 - config.STOP_LOSS_PCT)
        self.take_profit   = price * (1 + config.TAKE_PROFIT_PCT)
        log.info(f"[{self.symbol}] OPEN @ {price:.2f}  TS={self.trailing_stop:.2f}  TP={self.take_profit:.2f}")

    def check_exit(self, price) -> str:
        if not self.active:
            return "HOLD"
        if price > self.peak_price:
            self.peak_price    = price
            self.trailing_stop = price * (1 - config.TRAILING_STOP_PCT)
        if price <= self.trailing_stop:
            return "TRAIL_STOP"
        if price >= self.take_profit:
            return "TAKE_PROFIT"
        return "HOLD"

    def close(self, was_loss: bool = False):
        self.active = False
        if was_loss:
            self.cooldown = config.COOLDOWN_CANDLES
            log.info(f"[{self.symbol}] Cooldown: {self.cooldown} intervals")

    def tick_cooldown(self):
        if self.cooldown > 0:
            self.cooldown -= 1

    def ready(self) -> bool:
        return not self.active and self.cooldown == 0


def run():
    exchange  = connect()
    positions = {s: Position(s) for s in config.SYMBOLS}
    log.info(f"Bot started | pairs: {config.SYMBOLS} | {config.TIMEFRAME}")

    while True:
        for symbol in config.SYMBOLS:
            try:
                df    = fetch_ohlcv(exchange, symbol)
                price = df["close"].iloc[-1]
                pos   = positions[symbol]
                pos.tick_cooldown()

                exit_reason = pos.check_exit(price)
                if exit_reason in ("TRAIL_STOP", "TAKE_PROFIT"):
                    log.info(f"[{symbol}] EXIT {exit_reason} @ {price:.2f}")
                    place_order(exchange, "sell", symbol, price)
                    was_loss = price < pos.entry_price
                    pos.close(was_loss=was_loss)

                elif pos.ready():
                    signal = get_signal(df, config.RSI_PERIOD, config.RSI_OVERSOLD, config.RSI_OVERBOUGHT)
                    log.info(f"[{symbol}] price={price:.2f}  signal={signal}")
                    if signal == "BUY":
                        if place_order(exchange, "buy", symbol, price):
                            pos.open(price)
                elif pos.cooldown > 0:
                    log.info(f"[{symbol}] Cooldown: {pos.cooldown} intervals remaining")
                else:
                    log.info(f"[{symbol}] price={price:.2f}  "
                             f"trail={pos.trailing_stop:.2f}  TP={pos.take_profit:.2f}")

            except Exception as e:
                log.error(f"[{symbol}] Error: {e}")

        time.sleep(config.CHECK_INTERVAL)


if __name__ == "__main__":
    run()
