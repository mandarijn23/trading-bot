# 🚀 PRODUCTION DEPLOYMENT CHECKLIST

**Status:** 🔴 **DO NOT DEPLOY TO LIVE TRADING YET**

This checklist must be completed 100% before any live trading.

---

## CRITICAL FIXES APPLIED

- [x] ✅ Fixed lookahead bias in multi-timeframe analysis
- [x] ✅ Added streak-based position scaling
- [x] ✅ Fixed ML data leakage in label creation
- [x] ✅ Added consecutive loss limit circuit breaker
- [x] ✅ Added risk of ruin calculator
- [ ] ⏳ Add order confirmation logic (NEED TO DO)
- [ ] ⏳ Add walk-forward validation harness (NEED TO ADD)

---

## PHASE 1: CODE VALIDATION

### Unit Tests
- [ ] Run `python -m pytest tests/` - all tests pass
- [ ] Verify no import errors: `python -c "import bot; import strategy; import risk_manager"`
- [ ] Check indicators work: 
  ```python
  from indicators import Indicators
  df = pd.DataFrame(...)  # Your data
  rsi = Indicators.rsi(df['close'], 14)
  atr = Indicators.atr(df, 14)
  assert len(rsi) == len(df), "RSI length mismatch"
  ```

### Syntax Validation
- [ ] All files compile without errors
- [ ] No undefined variables in strategy module
- [ ] Config file is valid YAML/JSON

### Risk Manager Tests
```python
from risk import RiskManager
from risk_of_ruin import RiskOfRuinCalculator

# Test consecutive loss detection
mgr = RiskManager(config)
mgr.update_trade_result(False)
mgr.update_trade_result(False)
mgr.update_trade_result(False)
multiplier = mgr.get_position_size_multiplier()
assert multiplier < 1.0, "Position should be scaled down"

# Test risk of ruin
analysis = RiskOfRuinCalculator.calculate(
    win_rate=0.55,
    avg_win_pct=0.02,
    avg_loss_pct=0.02
)
assert analysis.probability_of_ruin < 0.15, "Ruin probability too high"
```

---

## PHASE 2: BACKTEST VALIDATION

### Run Complete Backtest
```bash
python backtest.py --symbol BTC/USDT --days 365 --fees --slippage
```

**Must Meet These Minimums:**
- [ ] Win rate: >= 45% (real, not fake)
- [ ] Profit factor: >= 1.5x (total wins / total losses)
- [ ] Max drawdown: <= 25%
- [ ] Sharpe ratio: >= 0.5
- [ ] Calmar ratio: >= 0.5
- [ ] Number of trades: >= 50 (need statistically significant)

**Suspicious Results (FAIL if any):**
- [ ] Win rate > 70% (probably overfitting or lookahead bias)
- [ ] Sharpe ratio > 3.0 (almost certainly fake)
- [ ] Zero drawdown (IMPOSSIBLE - ignore results)
- [ ] Perfect consecutive wins/losses (not realistic)

### Walk-Forward Validation
```python
from backtest import ProfessionalBacktester

backtest_engine = ProfessionalBacktester(config)
results = backtest_engine.walk_forward_analysis(
    df, "BTC/USDT",
    train_size=200,
    test_size=50,
    step_size=25
)

# Check performance decay
in_sample_wr = np.mean([m.win_rate for m in results["in_sample_metrics"]])
out_of_sample_wr = np.mean([m.win_rate for m in results["out_of_sample_metrics"]])
decay = (in_sample_wr - out_of_sample_wr) / in_sample_wr

print(f"In-sample WR: {in_sample_wr:.1%}")
print(f"Out-of-sample WR: {out_of_sample_wr:.1%}")
print(f"Decay: {decay:.1%}  ← Should be < 30%")
```

**Must Pass:**
- [ ] Out-of-sample decay: < 30% (< 20% is excellent)
- [ ] Out-of-sample win rate: >= 40%
- [ ] Strategy works in multiple market regimes (bullish, bearish, sideways)

**Fail Conditions:**
- [ ] Decay > 50% (strategy is severely overfit)
- [ ] Out-of-sample win rate < 35%
- [ ] Performs well only in bull markets (not regime-robust)

---

## PHASE 3: ML MODEL VALIDATION

### Test for Data Leakage
```python
from ml_model import FeatureEngineer, DataSplitter

# Create features and labels WITHOUT leakage
X = FeatureEngineer.create_features(df, lookback=20)
y = FeatureEngineer.create_labels(df, lookahead_bars=5)  # ✅ This is fixed

# Split
(X_train, y_train), (X_val, y_val), (X_test, y_test) = DataSplitter.train_val_test_split(X, y)

# Train
model = NeuralNetwork()
model.train(X_train, y_train, X_val, y_val)

# Test on unseen data
test_accuracy = model.evaluate(X_test, y_test)

print(f"Train accuracy: {model.train_accuracy:.1%}")
print(f"Test accuracy: {test_accuracy:.1%}")
```

**Must Meet:**
- [ ] Test accuracy: 45-55% (realistic, not fake 70%+)
- [ ] Train accuracy only 2-5% higher than test (minimal overfitting)
- [ ] Model performance beats random (>50% for 2-class)

---

## PHASE 4: RISK OF RUIN ANALYSIS

### Calculate Account Blowup Probability
```python
from risk_of_ruin import RiskOfRuinCalculator

analysis = RiskOfRuinCalculator.calculate(
    win_rate=0.52,  # From backtest
    avg_win_pct=0.015,  # From backtest
    avg_loss_pct=0.015,  # From backtest
    num_simulations=10000
)

print(analysis)
```

**Must Pass:**
- [ ] Probability of ruin: < 10% (aim for < 5%)
- [ ] Expected time to ruin: > 12 months
- [ ] Trades until safe: <= 500

**Fail Conditions:**
- [ ] Probability of ruin > 20%
- [ ] Expected time to ruin < 3 months
- [ ] Strategy is mathematically unprofitable

---

## PHASE 5: STRESS TESTING

### Test Edge Cases
```python
from backtest import ProfessionalBacktester

# Test 1: Flash crash (20% drop in 1 bar)
# Test 2: High volatility (ATR spike 3x)
# Test 3: Low liquidity (bid-ask spread 1%)
# Test 4: Few trades per day (less opportunity)
```

**Must Survive:**
- [ ] 20% flash crash: Account doesn't blow up
- [ ] 3x volatility spike: Position sizing scales down
- [ ] 1% spreads: Still profitable
- [ ] Low trade frequency: Strategy adapts

---

## PHASE 6: PAPER TRADING (4 WEEKS MINIMUM)

**Important:** Use real data, real order simulation, but no real money.

### Week 1: Baseline Collection
- [ ] Trade on paper for 7 days
- [ ] Collect 30+ trades
- [ ] Verify signals match strategy
- [ ] Check execution prices vs expected

### Week 2: Performance Comparison
- [ ] Compare paper results to backtest
- [ ] Calculate paper win rate
- [ ] Should be within 10% of backtest

**Red Flags:**
- [ ] ❌ Paper win rate 20%+ lower than backtest = strategy is weaker
- [ ] ❌ Signals don't match strategy = code bug
- [ ] ❌ Can't execute orders = connectivity issue

### Week 3: Regime Testing
- [ ] Trade through at least 2 different market conditions
- [ ] Verify strategy adapts (auto-switches if multi-strategy)
- [ ] Check that losing trades are logged

### Week 4: Risk Monitoring
- [ ] Maximum drawdown < expected
- [ ] Win rate settling around expected
- [ ] No surprise losses or skipped trades
- [ ] Logging captures all decisions

**Must Pass Final Week:**
- [ ] Paper win rate: 40-55%
- [ ] Paper Sharpe ratio: > 0.3
- [ ] Paper drawdown: < 20%
- [ ] Zero execution failures

---

## PHASE 7: LIVE TRADING PREPARATION

### Risk Settings
```python
config = {
    'starting_capital': 1000,  # START SMALL
    'max_risk_per_trade': 0.01,  # 1% (half of backtest)
    'max_daily_loss_pct': 0.03,  # 3% (tighter than backtest)
    'max_open_positions': 1,  # Only 1 trade at a time
    'max_consecutive_losses': 3,  # Strict circuit breaker
}
```

### Order Validation
- [ ] Dry-run orders through exchange API (don't execute)
- [ ] Verify order format accepted
- [ ] Check order confirmation timing
- [ ] Verify cancel order works

### Monitoring Setup
- [ ] Logging configured for all trades
- [ ] Email alerts on trades
- [ ] Slack notifications on errors
- [ ] Performance dashboard ready

---

## FINAL CHECKLIST: 30 ITEMS

- [ ] 1. All code reviewed by another trader
- [ ] 2. No lookahead bias in signals
- [ ] 3. No future data leakage in ML
- [ ] 4. Position sizing handles liquidity limits
- [ ] 5. Order confirmation logic implemented
- [ ] 6. Consecutive loss circuit breaker active
- [ ] 7. Risk of ruin < 15%
- [ ] 8. Backtest shows 45%+ win rate
- [ ] 9. Walk-forward validation passes (decay < 30%)
- [ ] 10. ML model accuracy is realistic (45-55%)
- [ ] 11. Sharpe ratio > 0.5 on backtest
- [ ] 12. Max drawdown < 25% on backtest
- [ ] 13. Paper trading results match expectations
- [ ] 14. Paper trading win rate 40-55%
- [ ] 15. Logging captured all decisions
- [ ] 16. No execution errors in paper trading
- [ ] 17. Strategy tested in bull market
- [ ] 18. Strategy tested in bear market
- [ ] 19. Strategy tested in sideways market
- [ ] 20. Stress tested on flash crash
- [ ] 21. Stress tested on high volatility
- [ ] 22. Stress tested on low liquidity
- [ ] 23. Configuration complete and validated
- [ ] 24. Risk manager tests pass
- [ ] 25. ML retraining enabled
- [ ] 26. Walk-forward analyzer configured
- [ ] 27. Order API tested (dry-run)
- [ ] 28. Monitoring/alerts configured
- [ ] 29. Contingency plan (how to stop bot) documented
- [ ] 30. Second opinion from experienced trader obtained

---

## GO/NO-GO DECISION

### Proceed to Live Trading IF:
- ✅ All 30 checklist items complete
- ✅ Walk-forward validation passes
- ✅ Paper trading results match backtest ±10%
- ✅ Risk of ruin < 15%
- ✅ Second opinion received

### DO NOT PROCEED IF:
- ❌ Any critical issues remain
- ❌ Backtest results seem too good to be true
- ❌ Paper trading diverges > 10% from backtest
- ❌ Multiple consecutive losses in first week of paper
- ❌ Code changes made right before deployment

---

## LIVE TRADING WITH SAFETY

### Initial Capital
- Start with SMALL capital ($500-$1,000)
- Risk 1% per trade (not 2%)
- Max 3% daily loss (not 5%)
- Only 1 open position at a time

### First Month
- Monitor trading daily
- Log all decisions
- Check accuracy matches backtest
- Verify no bugs

### Month 2+
- If profitable and stable, increase size gradually
- Add 10-20% more capital per month
- Monitor Sharpe ratio trend
- Continue logging

---

## ABORT SIGNALS (Stop Everything If):

- 🔴 Account drops > 15% before expected
- 🔴 Multiple orders rejected/fail
- 🔴 Signals stop coming (code crash)
- 🔴 Exchange connectivity issues
- 🔴 Win rate drops below 35%
- 🔴 Drawdown exceeds 25%

**IMMEDIATE ACTION:**
1. Kill all open positions
2. Disable trading
3. Review logs
4. Fix issues
5. Restart with paper trading

---

## SUCCESS METRICS (Track These)

**Monthly Targets:**
- Win rate: 50-60%
- Profit factor: > 1.8x
- Max drawdown: 10-20%
- Sharpe ratio: > 0.5

**Red Flags:**
- Win rate < 40%
- Sharpe < 0.2
- Consecutive losses > 10
- Drawdown > 30%

---

## DOCUMENTATION CHECKLIST

All files created and validated:
- [x] AUDIT_FINDINGS.md - Issues found and how serious
- [x] AUDIT_FIXES.md - Code solutions for each issue
- [x] risk_of_ruin.py - Risk of ruin calculator
- [ ] ⏳ PRODUCTION_CHECKLIST.md - This document
- [ ] DEPLOYMENT_LOG.md - What happened during go-live
- [ ] TRADING_JOURNAL.md - Track all trades and learning

---

**NEXT STEP:** Start Phase 1 code validation. Do NOT skip any steps.

When all 30 items are checked, schedule Zoom call with another trader for final review before proceeding.

