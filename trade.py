#!/usr/bin/env python3
"""
Stock Bot Launcher

Stock-only launcher for Alpaca paper/live stock workflow.

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
    """Let user choose action."""
    print("""
  Select action:

  1️⃣  📈 RUN STOCK BOT (SPY, QQQ, VOO)
  2️⃣  ⚙️  SETUP - Configure stock bot
  3️⃣  ✅ PREFLIGHT - Paper-trading launch checks
  4️⃣  📉 DAILY REPORT - Performance + decay
  """)

    choice = input("  Choose (1-4): ").strip()

    if choice == "1":
        return "stocks"
    elif choice == "2":
        return "setup"
    elif choice == "3":
        return "preflight"
    elif choice == "4":
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
    
    os.system("PYTHONPATH=core:models:strategies:utils:config python core/stock_bot.py")
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
            elif bot_type == "setup":
                return run_setup()
            elif bot_type == "preflight":
                os.system("python paper_launch_check.py")
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
