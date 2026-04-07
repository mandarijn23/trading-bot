#!/usr/bin/env python3
"""Debug script to test Alpaca data fetching."""

import os
import pandas as pd
import alpaca_trade_api as tradeapi
from dotenv import load_dotenv

load_dotenv()

api = tradeapi.REST(
    key_id=os.getenv("ALPACA_API_KEY"),
    secret_key=os.getenv("ALPACA_API_SECRET"),
    base_url=os.getenv("ALPACA_BASE_URL"),
)

print("Testing data fetch from Alpaca...")

try:
    bars = api.get_bars("SPY", "15min", limit=250).df
    print(f"\n✅ Fetched {len(bars)} bars")
    print(f"Columns: {list(bars.columns)}")
    print(f"Index: {bars.index.name}")
    print(f"\nFirst row:\n{bars.iloc[0]}")
    print(f"\nLast row:\n{bars.iloc[-1]}")
    
    # Reset index
    bars.reset_index(inplace=True)
    print(f"\n✅ After reset_index:")
    print(f"Columns: {list(bars.columns)}")
    print(f"Shape: {bars.shape}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
