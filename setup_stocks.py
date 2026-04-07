#!/usr/bin/env python3
"""
Stock Bot Setup Assistant

Helps you set up Alpaca API keys and configuration for paper trading.

Run: python setup_stocks.py
"""

import os
import sys
from pathlib import Path


def print_header(title: str) -> None:
    """Print formatted header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_step(num: int, text: str) -> None:
    """Print step number."""
    print(f"\n  {num}️⃣  {text}")


def get_api_keys() -> tuple[str, str]:
    """Get API keys from user."""
    print_step(1, "Get API Keys from Alpaca")
    print("""
    Go to: https://app.alpaca.markets
    
    1. Sign up (free account)
    2. Verify email
    3. Go to: Account Settings → API Keys
    4. Copy your API Key and Secret Key
    
    Leave this visible while continuing...
    """)
    
    api_key = input("  📌 Enter ALPACA_API_KEY: ").strip()
    api_secret = input("  📌 Enter ALPACA_API_SECRET: ").strip()
    
    if not api_key or not api_secret:
        print("  ❌ API keys required!")
        sys.exit(1)
    
    print(f"  ✅ API Key: {api_key[:20]}...")
    print(f"  ✅ Secret: {api_secret[:20]}...")
    
    return api_key, api_secret


def get_settings() -> dict:
    """Get trading settings."""
    print_step(2, "Configure Trading Settings")
    
    defaults = {
        "STOCK_TRADE_AMOUNT": 20.0,
        "STOCK_RSI_OVERSOLD": 35,
        "STOCK_TAKE_PROFIT": 0.05,
        "STOCK_PAPER_TRADING": True,
        "STOCK_USE_AI": True,
    }
    
    print(f"  Position size per trade: ${defaults['STOCK_TRADE_AMOUNT']} (keep small!)")
    print(f"  RSI buy threshold: {defaults['STOCK_RSI_OVERSOLD']} (keep 30-40)")
    print(f"  Profit target: {defaults['STOCK_TAKE_PROFIT']*100}% (5-10% good)")
    print(f"  Paper trading: {'Yes' if defaults['STOCK_PAPER_TRADING'] else 'No'}")
    print(f"  Use AI: {'Yes' if defaults['STOCK_USE_AI'] else 'No'}")
    
    custom = input("\n  Use defaults? (y/n): ").strip().lower()
    
    if custom == 'n':
        try:
            defaults["STOCK_TRADE_AMOUNT"] = float(input("  Position size ($): ") or 20.0)
            defaults["STOCK_TAKE_PROFIT"] = float(input("  Profit target (0.01-0.20): ") or 0.05)
        except ValueError:
            print("  ⚠️  Invalid input, using defaults")
    
    return defaults


def update_env_file(api_key: str, api_secret: str, settings: dict) -> None:
    """Update or create .env file."""
    print_step(3, "Update .env File")
    
    env_file = Path(".env")
    
    # Generate new content
    new_content = f"""# Stock Trading Bot Configuration
ALPACA_API_KEY={api_key}
ALPACA_API_SECRET={api_secret}
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# Stocks to trade
STOCK_SYMBOLS=SPY,QQQ,VOO
STOCK_TIMEFRAME=1h

# RSI Settings
STOCK_RSI_PERIOD=14
STOCK_RSI_OVERSOLD={int(settings['STOCK_RSI_OVERSOLD'])}
STOCK_RSI_OVERBOUGHT=65

# Position Size
STOCK_TRADE_AMOUNT={settings['STOCK_TRADE_AMOUNT']}

# Risk Management
STOCK_STOP_LOSS=0.03
STOCK_TAKE_PROFIT={settings['STOCK_TAKE_PROFIT']}
STOCK_TRAILING_STOP=0.02
STOCK_COOLDOWN=4

# Trading Mode
STOCK_PAPER_TRADING={str(settings['STOCK_PAPER_TRADING']).lower()}
STOCK_CHECK_INTERVAL=60
STOCK_LOG_LEVEL=INFO

# AI
STOCK_USE_AI={str(settings['STOCK_USE_AI']).lower()}
"""
    
    if env_file.exists():
        print(f"  📄 {env_file} exists, backing up to {env_file}.backup")
        os.rename(env_file, f"{env_file}.backup")
    
    with open(env_file, "w") as f:
        f.write(new_content)
    
    print(f"  ✅ Created .env with stock configuration")


def install_dependencies() -> None:
    """Install required packages."""
    print_step(4, "Install Dependencies")
    
    print("  Installing alpaca-trade-api...")
    os.system("pip install alpaca-trade-api>=3.0.0 -q")
    
    print("  ✅ Dependencies installed!")


def test_connection(api_key: str, api_secret: str) -> bool:
    """Test Alpaca connection."""
    print_step(5, "Test Alpaca Connection")
    
    try:
        import alpaca_trade_api as tradeapi
        
        api = tradeapi.REST(
            api_key=api_key,
            secret_key=api_secret,
            base_url="https://paper-api.alpaca.markets"
        )
        
        account = api.get_account()
        print(f"  ✅ Connected to Alpaca!")
        print(f"  💰 Paper trading balance: ${float(account.buying_power):,.2f}")
        return True
    except Exception as e:
        print(f"  ❌ Connection failed: {e}")
        print(f"  Check your API keys in .env")
        return False


def show_next_steps() -> None:
    """Show what to do next."""
    print_header("✅ Setup Complete!")
    
    print("""
  Next steps:
  
  1. Check .env file:
     cat .env
  
  2. Run the stock bot:
     python stock_bot.py
  
  3. Watch it trade real stocks! 🚀
  
  4. Monitor logs:
     tail -f stock_bot.log
  
  5. Check AI performance:
     python ai_manage.py stats
  
  ⏰ Remember: Market hours only (9:30 AM - 4:00 PM EST, Mon-Fri)
  
  📚 Full guide: Read STOCK_QUICKSTART.md
  """)


def main() -> None:
    """Main setup flow."""
    print_header("🤖 Stock Bot Setup Assistant")
    
    print("""
  This will help you:
  
  ✅ Get Alpaca API keys
  ✅ Configure paper trading
  ✅ Install dependencies
  ✅ Test connection
  ✅ Start trading stocks!
  """)
    
    input("\n  Press ENTER to start setup...")
    
    try:
        # Get settings
        api_key, api_secret = get_api_keys()
        settings = get_settings()
        
        # Update files
        update_env_file(api_key, api_secret, settings)
        install_dependencies()
        
        # Test
        if test_connection(api_key, api_secret):
            show_next_steps()
        else:
            print("\n  ⚠️  Connection test failed. Check your API keys and try again.")
            print("  You can edit .env and retry: python setup_stocks.py")
    
    except KeyboardInterrupt:
        print("\n\n  ❌ Setup cancelled")
        sys.exit(1)
    except Exception as e:
        print(f"\n  ❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
