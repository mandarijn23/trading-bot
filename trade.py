#!/usr/bin/env python3
"""
Universal Bot Launcher

Choose whether to trade crypto or stocks with one command.

Run: python trade.py
"""

import sys
import os
from pathlib import Path


def print_header() -> None:
    """Print header."""
    print("\n" + "=" * 60)
    print("  🤖 Trading Bot Launcher")
    print("=" * 60)


def choose_bot() -> str:
    """Let user choose bot."""
    print("""
  What do you want to trade?

  1️⃣  📈 STOCKS (SPY, QQQ, VOO) - Paper trading, NO real money
  2️⃣  🪙 CRYPTO (BTC, ETH, SOL) - Binance (paper or live)

  Or:

  3️⃣  🧪 BACKTEST - Test strategy on historical data
  4️⃣  🤖 AI TOOLS - Manage AI model
  5️⃣  ⚙️  SETUP - Configure bot
  6️⃣  ✅ PREFLIGHT - Paper-trading launch checks
  7️⃣  📉 DAILY REPORT - Performance + decay
  """)

    choice = input("  Choose (1-7): ").strip()

    if choice == "1":
        return "stocks"
    elif choice == "2":
        return "crypto"
    elif choice == "3":
        return "backtest"
    elif choice == "4":
        return "ai"
    elif choice == "5":
        return "setup"
    elif choice == "6":
        return "preflight"
    elif choice == "7":
        return "daily_report"
    else:
        print("  ❌ Invalid choice")
        return ""


def run_stocks() -> int:
    """Run stock bot."""
    print("\n  Starting stock trading bot...")
    print("  📌 Make sure Alpaca API keys are in .env")
    print("  ⏰ Market hours: 9:30 AM - 4:00 PM EST (Mon-Fri)\n")
    
    # Check if API key exists
    if not os.getenv("ALPACA_API_KEY"):
        print("  ❌ ALPACA_API_KEY not found in .env")
        print("  Run: python setup_stocks.py")
        return 1
    
    os.system("python stock_bot.py")
    return 0


def run_crypto() -> int:
    """Run crypto bot."""
    print("\n  Starting crypto trading bot...")
    print("  📌 Make sure Binance API keys are in .env")
    print("  ✅ 24/7 trading available\n")
    
    # Check if API key exists
    if not os.getenv("BINANCE_API_KEY"):
        print("  ❌ BINANCE_API_KEY not found in .env")
        print("  Add keys to .env and try again")
        return 1
    
    os.system("python bot.py")
    return 0


def run_backtest() -> int:
    """Run backtest."""
    print("""
  Backtest Options:
  
  1️⃣  Standard strategy (RSI + 200 MA)
  2️⃣  AI-enhanced strategy
  3️⃣  Compare both
  """)
    
    choice = input("  Choose (1-3): ").strip()
    
    if choice == "1":
        os.system("python backtest.py")
    elif choice == "2":
        os.system("python backtest.py --ai-enhanced")
    elif choice == "3":
        os.system("python backtest.py --compare-ai")
    else:
        print("  ❌ Invalid choice")
        return 1
    
    return 0


def run_ai() -> int:
    """AI management."""
    print("""
  AI Management:
  
  1️⃣  Show stats
  2️⃣  Train model
  3️⃣  Reset model
  """)
    
    choice = input("  Choose (1-3): ").strip()
    
    if choice == "1":
        os.system("python ai_manage.py stats")
    elif choice == "2":
        symbol = input("  Symbol (default=BTC/USDT): ").strip() or "BTC/USDT"
        epochs = input("  Epochs (default=20): ").strip() or "20"
        os.system(f"python ai_manage.py train {symbol} {epochs}")
    elif choice == "3":
        os.system("python ai_manage.py reset")
    else:
        print("  ❌ Invalid choice")
        return 1
    
    return 0


def run_setup() -> int:
    """Run setup."""
    print("""
  Setup Options:
  
  1️⃣  Stock bot setup (Alpaca)
  2️⃣  Validate setup
  """)
    
    choice = input("  Choose (1-2): ").strip()
    
    if choice == "1":
        os.system("python setup_stocks.py")
    elif choice == "2":
        os.system("python validate_setup.py")
    else:
        print("  ❌ Invalid choice")
        return 1
    
    return 0


def main() -> int:
    """Main launcher."""
    try:
        print_header()
        
        while True:
            bot_type = choose_bot()
            
            if not bot_type:
                continue
            
            print()
            
            if bot_type == "stocks":
                return run_stocks()
            elif bot_type == "crypto":
                return run_crypto()
            elif bot_type == "backtest":
                return run_backtest()
            elif bot_type == "ai":
                return run_ai()
            elif bot_type == "setup":
                return run_setup()
            elif bot_type == "preflight":
                os.system("python paper_launch_check.py --mode auto")
                return 0
            elif bot_type == "daily_report":
                os.system("python daily_performance_report.py")
                return 0
    
    except KeyboardInterrupt:
        print("\n\n  ❌ Cancelled")
        return 1
    except Exception as e:
        print(f"\n  ❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
