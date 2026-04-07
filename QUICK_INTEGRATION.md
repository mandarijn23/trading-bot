"""
QUICK INTEGRATION GUIDE
=======================

How to use all the new professional modules together in your trading bot.

STEP 1: IMPORT THE NEW MODULES
==============================

from indicators import Indicators, MarketRegime
from multi_timeframe import MultiTimeframeAnalyzer, TimeframeFilter
from strategy import StrategyManager, MeanReversionStrategy, TrendFollowingStrategy
from risk import RiskManager, TradeValidator, PositionSize
from backtest import ProfessionalBacktester, BacktestConfig


STEP 2: INITIALIZE COMPONENTS
==============================

# Create risk manager
risk_mgr = RiskManager(config)

# Create strategy manager (auto-selects best strategy for market regime)
strategy_mgr = StrategyManager()

# Create multi-timeframe analyzer
mta = MultiTimeframeAnalyzer(["4h", "1h", "15m"])

# Create backtest engine (for validation)
bt_config = BacktestConfig()
backtest_engine = ProfessionalBacktester(bt_config)


STEP 3: MAIN TRADING LOOP EXAMPLE
==================================

async def trade_loop(bot):
    \"\"\"Main trading loop with professional components.\"\"\"
    
    while True:
        try:
            # Fetch market data
            df_4h = await fetch_data("BTC/USDT", "4h", limit=500)
            df_1h = await fetch_data("BTC/USDT", "1h", limit=500)
            df_15m = await fetch_data("BTC/USDT", "15m", limit=500)
            
            # STEP 1: Multi-timeframe analysis
            mta.add_timeframe_data("4h", df_4h)
            mta.add_timeframe_data("1h", df_1h)
            mta.add_timeframe_data("15m", df_15m)
            
            all_signals = mta.analyze_all()
            combined_signal = mta.get_combined_signal()
            confluence = mta.get_confluence_score()
            
            print(f"Multi-TF Signal: {combined_signal}")
            print(f"Confluence: {confluence:.0%}")
            print(mta.get_summary())
            
            # STEP 2: Risk checks (before entry)
            allowed, reason = risk_mgr.check_pre_trade(
                portfolio,
                symbol="BTC/USDT",
                open_positions=len(portfolio.positions)
            )
            
            if not allowed:
                print(f"Trade blocked: {reason}")
                await asyncio.sleep(60)
                continue
            
            # STEP 3: Get strategy signal
            strategy_mgr.update_data(df_1h)  # Use 1h as primary
            strategy_signal = strategy_mgr.get_signal(df_1h)
            
            print(f"Strategy: {strategy_mgr.select_strategy(df_1h)}")
            print(f"Signal: {strategy_signal.signal}")
            print(f"Confidence: {strategy_signal.confidence:.0%}")
            print(f"Reason: {strategy_signal.reason}")
            
            # STEP 4: Combine signals (multi-TF + strategy)
            if combined_signal != strategy_signal.signal:
                print("⚠️ Multi-TF and strategy disagree, suppressing signal")
                await asyncio.sleep(60)
                continue
            
            if confluence < 0.5:  # Need at least 50% confluence
                print("⚠️ Low confluence score, suppressing signal")
                await asyncio.sleep(60)
                continue
            
            # STEP 5: Position sizing
            pos_size = risk_mgr.calculate_position_size(
                portfolio,
                entry_price=strategy_signal.entry_price,
                stop_loss_price=strategy_signal.stop_loss,
                symbol="BTC/USDT",
                atr_value=strategy_signal.atr
            )
            
            if pos_size.shares <= 0:
                print(f"Position too small: {pos_size.reason}")
                await asyncio.sleep(60)
                continue
            
            print(f"Position size: {pos_size.shares} ({pos_size.reason})")
            
            # STEP 6: Validate entry
            valid, msg = TradeValidator.validate_entry(
                strategy_signal.entry_price,
                strategy_signal.stop_loss,
                strategy_signal.take_profit,
                min_reward_risk_ratio=1.5
            )
            
            if not valid:
                print(f"Entry validation failed: {msg}")
                await asyncio.sleep(60)
                continue
            
            # STEP 7: Place order
            if strategy_signal.signal == "BUY":
                order = await place_order(
                    symbol="BTC/USDT",
                    side="BUY",
                    amount=pos_size.shares,
                    price=strategy_signal.entry_price,
                    stop_loss=strategy_signal.stop_loss,
                    take_profit=strategy_signal.take_profit
                )
                
                if order:
                    print(f"✅ Buy order placed: {order.id}")
                    portfolio.open_position(...)
            
            # Wait before next check
            await asyncio.sleep(60)
        
        except Exception as e:
            logger.error(f"Trading error: {e}", exc_info=True)
            await asyncio.sleep(60)


STEP 4: BACKTESTING WITH NEW MODULES
====================================

def backtest_with_all_features(symbol="BTC/USDT"):
    \"\"\"Backtest with professional features.\"\"\"
    
    # Fetch data
    df = fetch_history(symbol, "1h", limit=1000)
    
    # Initialize backtest engine
    bt_config = BacktestConfig()
    backtest = ProfessionalBacktester(bt_config)
    
    # Run backtest
    trades, metrics = backtest.backtest(
        df,
        symbol,
        use_fees=True,
        use_slippage=True  # ← Key: realistic simulation
    )
    
    # Print results
    print(metrics)
    
    # Show recent trades
    for trade in trades[-5:]:
        print(trade)


STEP 5: COMPARING STRATEGIES
============================

def compare_strategies():
    \"\"\"Compare different strategies on same data.\"\"\"
    
    df = fetch_history("BTC/USDT", "1h", limit=1000)
    
    strategies = {
        "mean_reversion": MeanReversionStrategy(),
        "trend_following": TrendFollowingStrategy(),
        "breakout": BreakoutStrategy(),
    }
    
    results = {}
    
    for name, strategy in strategies.items():
        trades = []
        capital = 10000
        
        for i in range(200, len(df)):
            signal = strategy.get_signal(df.iloc[:i+1])
            
            if signal.signal == "BUY":
                # Simple backtest
                entry = signal.entry_price
                exit_price = df["close"].iloc[i+5]  # 5 candles later
                pnl = (exit_price - entry) * 1  # 1 unit
                trades.append(pnl)
        
        total_pnl = sum(trades)
        win_rate = len([t for t in trades if t > 0]) / len(trades) * 100
        
        results[name] = {
            "trades": len(trades),
            "total_pnl": total_pnl,
            "win_rate": win_rate,
        }
    
    # Print comparison
    for name, stats in results.items():
        print(f"{name}: {stats['trades']} trades, "
              f"WR={stats['win_rate']:.1f}%, "
              f"PnL=${stats['total_pnl']:.2f}")


STEP 6: MONITORING & OPTIMIZATION
=================================

def analyze_trading_performance():
    \"\"\"Track and optimize performance.\"\"\"
    
    # Check daily stats
    stats = risk_mgr.get_stats()
    print(f"Today's trades: {stats['today_trades']}")
    print(f"Win rate: {stats['today_win_rate']:.1f}%")
    
    # Check circuit breaker status
    if risk_mgr.circuit_breaker_active:
        print(f"⚠️ Circuit breaker is ACTIVE")
        print(f"Will reset at: {risk_mgr.circuit_breaker_until}")
    
    # Check portfolio
    print(f"Equity: ${portfolio.equity:,.2f}")
    print(f"Daily P&L: ${portfolio.daily_pnl():,.2f}")
    print(f"Daily DD: {portfolio.daily_drawdown_pct():.2f}%")
    print(f"Total return: {portfolio.total_return_pct():.2f}%")
    
    # Identify best performing strategy
    strategy_stats = analyze_strategy_performance()
    best_strategy = max(strategy_stats, key=lambda x: x['win_rate'])
    print(f"Best strategy: {best_strategy['name']} ({best_strategy['win_rate']:.1f}%)")


RECOMMENDED WORKFLOW
====================

Day 1-3: BACKTEST & VALIDATE
- Use ProfessionalBacktester with realistic fees/slippage
- Test 3 different strategy combinations
- Check Sharpe ratio, drawdown, win rate
- Only proceed if metrics meet your standards

Day 4-7: PAPER TRADE VALIDATION
- Paper trade with real-time data for 4-7 days
- Verify risk management works properly
- Check that multi-timeframe filtering improves results
- Monitor for any unexpected patterns

Week 2+: PAPER TRADE MONITORING
- Run for at least 2-4 weeks to get statistical significance
- Track win rate, average win/loss, Sharpe ratio
- Adjust parameters if needed
- Only then consider live trading

LIVE TRADING (when ready):
- Start with minimum position size
- Scale up gradually after 2-4 weeks
- Keep monitoring drawdown and win rate
- Adjust risk parameters if needed


KEY METRICS TO TRACK
====================

✅ Win Rate: Target 50-65%
✅ Profit Factor: Target 1.5x+ (wins / losses)
✅ Sharpe Ratio: Target 1.0+
✅ Max Drawdown: Keep < 15%
✅ Recovery Factor: Target 3.0+ (profit / max loss)
✅ Calmar Ratio: Target 0.5+

If any metric is below target:
1. Add more filters (trend, volume, volatility)
2. Use multi-timeframe confirmation
3. Adjust position sizing
4. Review strategy selection logic
5. Back-test on more historical data


COMMON ISSUES & SOLUTIONS
==========================

Issue: "High backtest return but low live performance"
Solution: You had future-leakage or unrealistic assumptions
→ Ensure proper train/val/test split (ml_model.py)
→ Include realistic fees/slippage in backtest
→ Test with walk-forward validation

Issue: "Too many losing trades"
Solution: Entry signals are too frequent or low quality
→ Add more filters (volume, trend, correlation)
→ Increase confluence requirement in multi-timeframe
→ Switch to TrendFollowingStrategy for trending markets

Issue: "Large drawdowns"
Solution: Position sizing is too aggressive
→ Reduce max_risk_per_trade from 2% to 1% or 0.5%
→ Use circuit breaker (already implemented)
→ Add correlation filtering (already implemented)

Issue: "Overtrading"
Solution: Too many signals being generated
→ Increase filters strictness
→ Add trade cooldown after losses
→ Require higher confluence score


FINAL CHECKLIST
===============

Before going live:
[ ] Backtests show consistent profitability (3+ years data)
[ ] Sharpe ratio > 1.0
[ ] Max drawdown < 15%
[ ] Win rate 50%+
[ ] Profit factor > 1.5x
[ ] Paper trading validated for 2+ weeks
[ ] All risk management features enabled
[ ] Position sizing validated
[ ] Multi-timeframe analysis working
[ ] Circuit breaker tested
[ ] Monitoring & alerting set up
[ ] Trade logging enabled
[ ] Phone number for emergencies saved

You're now ready for professional trading!
"""