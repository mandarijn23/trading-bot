#!/usr/bin/env python3
"""
Trading Bot CLI Management Tool

Commands:
  python cli.py test-discord      - Test Discord webhook
  python cli.py retrain           - Force model retraining
  python cli.py reset-trades      - Clear trade history (⚠️  DANGEROUS)
  python cli.py stats             - Show AI performance stats
  python cli.py validate-config   - Verify environment setup
    python cli.py preflight         - Run paper-trading launch checklist
    python cli.py daily-report      - Run daily performance/decay report
"""

import sys
import os
import json
import subprocess
import click
from pathlib import Path
from datetime import datetime

ROOT_DIR = Path(__file__).resolve().parent
for rel in ("core", "models", "strategies", "utils", "config"):
    p = str(ROOT_DIR / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

from stock_config import load_stock_config
from discord_alerts import discord
from model_retrainer import ModelRetrainer, TradeAnalytics


@click.group()
def cli():
    """Trading Bot CLI Management Tool."""
    pass


@cli.command()
def test_discord():
    """Test Discord webhook connection."""
    click.echo("🔗 Testing Discord webhook...\n")
    
    if not discord.enabled:
        click.echo("❌ Discord not enabled!")
        click.echo("\nSetup Discord notifications:")
        click.echo("  1. Create a Discord server (if you don't have one)")
        click.echo("  2. Go to Server Settings → Integrations → Webhooks → New Webhook")
        click.echo("  3. Copy the webhook URL")
        click.echo("  4. Add to .env: DISCORD_WEBHOOK_URL=<your_webhook_url>")
        click.echo("\n  📖 Full guide: https://discord.com/developers/applications")
        return
    
    try:
        # Test 1: Basic message
        click.echo("Test 1: Sending test message...")
        result = discord.send_message(
            "🧪 Discord Integration Test",
            {
                "Status": "✅ Working",
                "Timestamp": datetime.now().isoformat(),
                "Bot": "Trading-Bot",
            }
        )
        if result:
            click.echo("  ✅ Basic message sent")
        else:
            click.echo("  ❌ Failed to send basic message")
            return
        
        # Test 2: Buy notification
        click.echo("Test 2: Sending BUY notification...")
        result = discord.notify_buy("BTC/USDT", 45000.0, 1, 0.75)
        if result:
            click.echo("  ✅ BUY notification sent")
        else:
            click.echo("  ❌ Failed to send BUY notification")
            return
        
        # Test 3: Sell notification
        click.echo("Test 3: Sending SELL notification...")
        result = discord.notify_sell("BTC/USDT", 45000.0, 46000.0, 1, 2.22, "TAKE_PROFIT")
        if result:
            click.echo("  ✅ SELL notification sent")
        else:
            click.echo("  ❌ Failed to send SELL notification")
            return
        
        # Test 4: Summary
        click.echo("Test 4: Sending daily summary...")
        result = discord.notify_daily_summary({
            "trades": 5,
            "wins": 4,
            "win_rate": "80%",
            "pnl": "+2.45%",
        })
        if result:
            click.echo("  ✅ Daily summary sent")
        else:
            click.echo("  ❌ Failed to send daily summary")
            return
        
        click.echo("\n✅ All Discord tests passed!")
        click.echo("🎉 Your trading bot is ready to send notifications!\n")
        
    except Exception as e:
        click.echo(f"❌ Discord test failed: {e}")
        sys.exit(1)


@cli.command("test-order")
@click.option("--symbol", default="SPY", show_default=True, help="Trading symbol")
@click.option("--qty", default=1, type=int, show_default=True, help="Order quantity")
@click.option("--side", default="buy", type=click.Choice(["buy", "sell"]), show_default=True, help="Order side")
def test_order(symbol: str, qty: int, side: str):
    """Submit a real Alpaca paper test order through the bot stack."""
    click.echo("🧪 Submitting paper test order via bot...\n")

    try:
        import alpaca_trade_api as tradeapi

        config = load_stock_config()
        config.paper_trading = True
        if symbol not in config.symbols:
            config.symbols = [symbol]

        api = tradeapi.REST(
            key_id=config.alpaca_api_key,
            secret_key=config.alpaca_api_secret,
            base_url=config.alpaca_base_url,
        )

        current_price = float(api.get_bars(symbol, config.timeframe, limit=5).df["close"].iloc[-1])
        click.echo(f"Current {symbol} price: {current_price:.2f}")

        order = api.submit_order(
            symbol=symbol,
            qty=qty,
            side=side,
            type="market",
            time_in_force="day",
        )

        click.echo(f"✅ Order submitted: {order.id}")
        click.echo(f"   Symbol: {order.symbol}")
        click.echo(f"   Side: {order.side}")
        click.echo(f"   Qty: {order.qty}")
        click.echo(f"   Status: {order.status}")
        click.echo(f"   Type: {order.type}")
        click.echo(f"   TIF: {order.time_in_force}")

        if discord:
            if side == "buy":
                discord.notify_buy(symbol, current_price, qty, 0.50)
            else:
                discord.notify_sell(symbol, current_price, current_price, qty, 0.0, "TEST_ORDER")

    except Exception as e:
        click.echo(f"❌ Test order failed: {e}")
        sys.exit(1)


@cli.command()
def retrain():
    """Force model retraining."""
    click.echo("🧠 Starting model retraining...")
    
    try:
        from ml_model_rf import TradingAI
        
        ai = TradingAI()
        retrainer = ModelRetrainer(retrain_interval=1)  # Force retrain
        
        # Load trade history
        history = retrainer.load_trade_history()
        if history.empty:
            click.echo("❌ No trade history found. Execute some trades first.")
            return
        
        click.echo(f"📊 Loaded {len(history)} trades")
        
        # Retrain
        retrainer.retrain_model(ai)
        click.echo("✅ Model retraining complete!")
        
        # Show stats
        stats = ai.get_stats()
        click.echo(f"\n📈 Updated AI Stats:")
        for key, value in stats.items():
            click.echo(f"   {key}: {value}")
        
    except Exception as e:
        click.echo(f"❌ Retraining failed: {e}")
        sys.exit(1)


@cli.command()
def stats():
    """Show AI performance statistics."""
    click.echo("📊 AI Performance Statistics\n")
    
    try:
        from ml_model_rf import TradingAI
        
        ai = TradingAI()
        stats = ai.get_stats()
        
        # Pretty print
        for key, value in stats.items():
            click.echo(f"  {key:.<30} {value}")
        
        # Load trade history stats
        retrainer = ModelRetrainer()
        history = retrainer.load_trade_history()
        
        if not history.empty:
            click.echo("\n📈 Trade History Analysis:")
            summary = TradeAnalytics.get_summary(history)
            for key, value in summary.items():
                click.echo(f"  {key:.<30} {value}")
        
    except Exception as e:
        click.echo(f"❌ Error loading stats: {e}")
        sys.exit(1)


@cli.command()
def validate_config():
    """Validate environment configuration."""
    click.echo("✅ Validating configuration...\n")
    
    errors = []
    warnings = []
    
    # Check .env file
    if not Path(".env").exists():
        errors.append("❌ .env file not found (copy from .env.example)")
    
    # Try loading stock config
    try:
        config = load_stock_config()
        click.echo(f"✅ Stock config loaded:")
        click.echo(f"   Symbols: {config.symbols}")
        click.echo(f"   Timeframe: {config.timeframe}")
        click.echo(f"   Paper trading: {config.paper_trading}")
    except Exception as e:
        errors.append(f"❌ Stock config error: {e}")
    
    # Check Discord
    try:
        if discord:
            click.echo(f"✅ Discord integration: Available")
        else:
            warnings.append("⚠️  Discord integration: Not available (optional)")
    except Exception as e:
        warnings.append(f"⚠️  Discord error: {e}")
    
    # Check AI model
    try:
        from ml_model_rf import TradingAI
        ai = TradingAI()
        click.echo(f"✅ AI model (Random Forest): Available")
    except ImportError:
        warnings.append("⚠️  Random Forest not available, trying TensorFlow...")
        try:
            from ml_model import TradingAI
            click.echo(f"✅ AI model (TensorFlow): Available")
        except ImportError:
            errors.append("❌ No AI model available (install tensorflow or scikit-learn)")
    
    # Check trade history
    if Path("trades_history.csv").exists():
        click.echo(f"✅ Trade history: Found (trades_history.csv)")
    else:
        click.echo(f"⚠️  Trade history: Not created yet (will generate on first trade)")
    
    # Report
    click.echo("\n" + "="*50)
    if errors:
        click.echo("\n🔴 ERRORS (must fix):")
        for error in errors:
            click.echo(f"   {error}")
        sys.exit(1)
    
    if warnings:
        click.echo("\n🟡 WARNINGS (optional):")
        for warning in warnings:
            click.echo(f"   {warning}")
    
    click.echo("\n✅ Configuration is valid! Ready to trade.")


@cli.command()
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
def reset_trades(yes: bool):
    """Reset trade history (WARNING: Destructive)."""
    if not yes:
        confirmed = click.confirm("🚨 This will DELETE all trade history. Continue?", default=False)
        if not confirmed:
            click.echo("Cancelled.")
            return

    csv_file = Path("trades_history.csv")
    pkl_file = Path("trading_model_rf.pkl")
    
    if csv_file.exists():
        csv_file.unlink()
        click.echo(f"🗑️  Deleted {csv_file}")
    
    if pkl_file.exists():
        pkl_file.unlink()
        click.echo(f"🗑️  Deleted {pkl_file}")
    
    click.echo("\n✅ Trade history reset. Model will retrain from next trades.")


@cli.command()
def analyze():
    """Detailed trade analysis (same as dashboard.py)."""
    click.echo("📊 Trade Analysis\n")
    
    try:
        from dashboard import (
            load_trades, analyze_overall, analyze_by_symbol,
            analyze_daily, analyze_recent_trades
        )
        
        df = load_trades()
        analyze_overall(df)
        analyze_by_symbol(df)
        analyze_daily(df)
        analyze_recent_trades(df)
        
    except Exception as e:
        click.echo(f"❌ Analysis failed: {e}")
        sys.exit(1)


@cli.command()
def version():
    """Show version info."""
    click.echo("Trading Bot v1.0.0 (Phase 6)")
    click.echo("Features: Async Crypto + Stock Trading with AI + Discord + Retraining")


@cli.command("preflight")
@click.option("--mode", type=click.Choice(["auto", "crypto", "stocks"]), default="auto", show_default=True)
def preflight(mode: str):
    """Run paper-trading preflight checklist."""
    result = subprocess.run(
        [sys.executable, "paper_launch_check.py", "--mode", mode],
        check=False,
    )
    if result.returncode != 0:
        sys.exit(1)


@cli.command("daily-report")
@click.option("--json-output", is_flag=True, help="Print JSON report")
def daily_report(json_output: bool):
    """Run daily performance and strategy-decay report."""
    cmd = [sys.executable, "daily_performance_report.py"]
    if json_output:
        cmd.append("--json")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        sys.exit(1)


def main():
    """Entry point."""
    if len(sys.argv) == 1:
        click.echo("Trading Bot CLI - Type 'python cli.py --help' for commands")
        sys.exit(0)
    
    cli()


if __name__ == "__main__":
    main()
