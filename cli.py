#!/usr/bin/env python3
"""
Trading Bot CLI Management Tool

Commands:
  python cli.py test-discord      - Test Discord webhook
  python cli.py retrain           - Force model retraining
  python cli.py reset-trades      - Clear trade history (⚠️  DANGEROUS)
  python cli.py stats             - Show AI performance stats
  python cli.py validate-config   - Verify environment setup
"""

import sys
import json
import click
from pathlib import Path
from datetime import datetime

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
    click.echo("🔗 Testing Discord webhook...")
    
    if not discord:
        click.echo("❌ Discord not initialized")
        return
    
    try:
        # Send test notification
        discord.notify_warning("✅ Discord webhook test successful!")
        click.echo("✅ Discord webhook is working!")
    except Exception as e:
        click.echo(f"❌ Discord webhook failed: {e}")
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
@click.confirmation_option(
    prompt="🚨 This will DELETE all trade history. Continue?",
    abort=True
)
def reset_trades():
    """Reset trade history (WARNING: Destructive)."""
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


def main():
    """Entry point."""
    if len(sys.argv) == 1:
        click.echo("Trading Bot CLI - Type 'python cli.py --help' for commands")
        sys.exit(0)
    
    cli()


if __name__ == "__main__":
    main()
