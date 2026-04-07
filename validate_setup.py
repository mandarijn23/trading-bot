"""
Quick validator for stock bot setup.

Run: python validate_setup.py
"""

import sys
import os
from pathlib import Path


def check_env_file() -> bool:
    """Check .env file exists and has required keys."""
    print("  📄 Checking .env file...")
    
    env_file = Path(".env")
    if not env_file.exists():
        print("    ❌ .env file not found!")
        print("    💡 Run: python setup_stocks.py")
        return False
    
    with open(env_file) as f:
        content = f.read()
    
    required_keys = [
        "ALPACA_API_KEY",
        "ALPACA_API_SECRET",
    ]
    
    missing = [k for k in required_keys if k not in content]
    if missing:
        print(f"    ❌ Missing keys: {missing}")
        return False
    
    print("    ✅ .env file configured")
    return True


def check_imports() -> bool:
    """Check required packages are installed."""
    print("  📦 Checking dependencies...")
    
    packages = {
        "pandas": "Data frames",
        "alpaca_trade_api": "Alpaca API",
        "tensorflow": "AI/ML (optional)",
    }
    
    missing = []
    for package, description in packages.items():
        try:
            __import__(package)
            print(f"    ✅ {package}")
        except ImportError:
            if package == "tensorflow":
                print(f"    ⚠️  {package} (optional, AI disabled)")
            else:
                missing.append(package)
                print(f"    ❌ {package}")
    
    if missing:
        print(f"\n  Install missing packages:")
        print(f"    pip install {' '.join(missing)}")
        return False
    
    return True


def check_files() -> bool:
    """Check required files exist."""
    print("  📁 Checking files...")
    
    files = [
        "stock_bot.py",
        "stock_config.py",
        "strategy.py",
    ]
    
    missing = [f for f in files if not Path(f).exists()]
    if missing:
        print(f"    ❌ Missing files: {missing}")
        return False
    
    for f in files:
        print(f"    ✅ {f}")
    
    return True


def test_alpaca_connection() -> bool:
    """Test Alpaca API connection."""
    print("  🔗 Testing Alpaca connection...")
    
    try:
        from stock_config import load_stock_config
        
        config = load_stock_config()
        print(f"    ✅ Config loaded")
        print(f"    ✅ Symbols: {config.symbols}")
        print(f"    ✅ Paper trading: {config.paper_trading}")
        
        # Try to import Alpaca
        try:
            import alpaca_trade_api as tradeapi
            api = tradeapi.REST(
                key_id=config.alpaca_api_key,
                secret_key=config.alpaca_api_secret,
                base_url=config.alpaca_base_url,
            )
            account = api.get_account()
            print(f"    ✅ Alpaca connected!")
            print(f"    💰 Balance: ${float(account.buying_power):,.2f}")
            return True
        except ImportError:
            print("    ⚠️  Alpaca not installed yet (will install on setup)")
            return True  # Not critical for validation
        except Exception as e:
            print(f"    ❌ Alpaca error: {e}")
            return False
    except Exception as e:
        print(f"    ❌ Config error: {e}")
        return False


def main() -> None:
    """Run all checks."""
    print("\n" + "=" * 60)
    print("  Stock Bot Setup Validator")
    print("=" * 60)
    
    checks = [
        ("Config", check_env_file),
        ("Files", check_files),
        ("Dependencies", check_imports),
        ("Alpaca", test_alpaca_connection),
    ]
    
    results = []
    for name, check_func in checks:
        print(f"\n{name}:")
        result = check_func()
        results.append((name, result))
    
    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    
    for name, result in results:
        status = "✅" if result else "❌"
        print(f"  {status} {name}")
    
    all_ok = all(r for _, r in results)
    
    if all_ok:
        print("\n  🎉 Everything ready! Run:")
        print("     python stock_bot.py")
    else:
        print("\n  ⚠️  Setup incomplete. Run:")
        print("     python setup_stocks.py")
    
    print("=" * 60 + "\n")
    
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
