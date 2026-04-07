# QUICK START: USING THE NEW STRATEGIES

**Goal:** Get up and running with quantitative edge strategies in 10 minutes  
**Complexity:** Easy  
**Time Required:** ~10 minutes to understand, 2 minutes to implement

---

## 🚀 QUICKEST START (2 Minutes to First Signal)

### Option 1: Drop-in Replacement

```python
# OLD CODE (still works)
from strategy import get_signal
signal = get_signal(df)

# NEW CODE (better)
from strategy_edge import EdgeStrategyManager
manager = EdgeStrategyManager()
signal_obj = manager.get_signal(df)

print(signal_obj.signal)        # "BUY", "HOLD", or "SELL"
print(signal_obj.reason)        # WHY the signal was generated
print(signal_obj.confidence)    # 0.0-1.0 (reliability)
```

**That's it.** One line change gets you all the new features.

---

## 📊 UNDERSTAND THE SIGNAL (5 Minutes)

### The New StrategySignal Object

```python
signal_obj = manager.get_signal(df)

# Trading decision
signal_obj.signal              # "BUY" / "HOLD" / "SELL"
signal_obj.confidence          # 0.0-1.0 probability of success
                               # 0.65 = weak, 0.85 = strong

# Entry and exits
signal_obj.entry_price         # Where to enter
signal_obj.stop_loss           # Where to stop out
signal_obj.take_profit         # Profit target
signal_obj.reason              # WHY signal generated

# Market context
signal_obj.regime              # Current market condition
                               # "TRENDING_UP", "RANGING_TIGHT", etc
signal_obj.atr                 # Current volatility
signal_obj.volume_confirm      # Is volume confirming? (bool)
signal_obj.signal_strength     # 0.0-1.0 quality of setup

# Analysis
signal_obj.rsi                 # Current RSI value
signal_obj.trend               # Which strategy is active?
```

### Example: What Each Signal Tells You

```
Signal: BUY
Confidence: 0.82
Reason: "Pullback in uptrend (RSI=45, EMA dist=0.8ATR)"
Regime: TRENDING_UP
Entry: 100.50
Stop: 98.00  (2.5% risk)
Target: 107.00  (6.5% reward)

→ 2.6:1 risk/reward ratio
→ Trend pullback strategy selected
→ 82% confidence = good setup
→ Plan: Enter at 100.50, stop at 98.00, target 107.00
```

---

## 🔧 IMPLEMENTATION EXAMPLES

### Example 1: Simple Usage (Just the Signal)

```python
import pandas as pd
from strategy_edge import EdgeStrategyManager

# Load your data
df = pd.read_csv("data.csv", index_col="date", parse_dates=True)

# Create manager
manager = EdgeStrategyManager()

# Get signal
signal_obj = manager.get_signal(df)

# Use it
if signal_obj.signal == "BUY":
    print(f"BUY at {signal_obj.entry_price}")
    print(f"Stop at {signal_obj.stop_loss}")
    print(f"Target at {signal_obj.take_profit}")
elif signal_obj.signal == "SELL":
    print(f"SELL at {signal_obj.entry_price}")
```

### Example 2: Dynamic Position Sizing

```python
# Position size based on confidence
base_size = 1.0  # 1 contract / 100 shares
position_size = base_size * signal_obj.confidence

print(f"Confidence: {signal_obj.confidence:.0%}")
print(f"Position Size: {position_size:.2f}")

# High confidence (0.85) → 0.85 size
# Low confidence (0.65) → 0.65 size
```

### Example 3: Regime-Based Portfolio

```python
# Different strategies for different regimes
if signal_obj.regime == "TRENDING_UP":
    # Use trend pullback strategy
    portfolio_allocation = 0.50  # 50% of capital to this regime

elif signal_obj.regime == "RANGING_TIGHT":
    # Use mean reversion strategy
    portfolio_allocation = 0.30  # 30% of capital

elif signal_obj.regime in ["RANGING_WIDE"]:
    # Use volatility breakout
    portfolio_allocation = 0.20  # 20% of capital
```

### Example 4: Filtering Bad Trades

```python
# Only trade high-confidence signals
MIN_CONFIDENCE = 0.70
MIN_SIGNAL_STRENGTH = 0.5

if signal_obj.signal != "HOLD":
    if signal_obj.confidence < MIN_CONFIDENCE:
        print("Signal too weak, skipping")
    elif signal_obj.signal_strength < MIN_SIGNAL_STRENGTH:
        print("Setup not fully formed, waiting")
    else:
        print("Trade signal GOOD, executing")
        # Execute trade
```

### Example 5: Risk Management

```python
# Position sizing with risk management
account_size = 10000  # Your account
risk_per_trade = 0.01  # 1% of account
max_position_size = account_size * 0.02  # 2% max

# Calculate position size from risk/reward
risk_amount = account_size * risk_per_trade  # $100 risk
entry_price = signal_obj.entry_price
stop_price = signal_obj.stop_loss
risk_per_share = entry_price - stop_price

position_size = risk_amount / risk_per_share
position_size = min(position_size, max_position_size)  # Cap it

print(f"Risk per trade: ${risk_amount}")
print(f"Position size: {position_size:.2f} shares")
print(f"Stop loss: ${stop_price}")
```

---

## ✅ VALIDATION (2 Minutes)

### Quick Backtest

```python
from strategy_validation import StrategyBacktester

# Create backtester
backtester = StrategyBacktester(
    commission=0.001,  # 0.1%
    slippage=0.002     # 0.2%
)

# Run backtest on your data
df = pd.read_csv("data.csv", index_col="date", parse_dates=True)
results = backtester.backtest(df)

# Print results
backtester.print_results(results)
```

### Expected Output

```
════════════════════════════════════════════
          STRATEGY EDGE VALIDATION RESULTS
════════════════════════════════════════════

VOLATILITY_MEAN_REVERSION - Regime: RANGING_TIGHT
────────────────────────────────────────────────────
  Trades:              45 total (28W / 17L)
  Win Rate:            62.2%
  Avg Win/Loss:        +1.52% / -1.18%
  Expectancy:          +0.5821% per trade
  Total Return:        +26.19%
  Profit Factor:       1.86
  Max Drawdown:        -12.34%
  Sharpe Ratio:        1.23
  Max Cons. Losses:    2
  Avg Holding:         8 bars

TREND_PULLBACK - Regime: TRENDING_UP
────────────────────────────────────────────────────
  Trades:              52 total (33W / 19L)
  Win Rate:            63.5%
  Avg Win/Loss:        +2.08% / -1.34%
  Expectancy:          +0.8502% per trade
  Total Return:        +44.21%
  Profit Factor:       2.41
  Max Drawdown:        -15.67%
  Sharpe Ratio:        1.45
  Max Cons. Losses:    2
  Avg Holding:         12 bars
```

---

## 🎯 REAL-WORLD INTEGRATION

### In Your Bot (bot.py)

```python
from strategy_edge import EdgeStrategyManager

class TradingBot:
    def __init__(self):
        self.strategy_manager = EdgeStrategyManager()
        self.open_trades = {}
    
    def on_new_candle(self, df):
        """Called when new candle completes."""
        
        # Get signal
        signal_obj = self.strategy_manager.get_signal(df)
        
        # Log for monitoring
        print(f"[{signal_obj.regime}] {signal_obj.reason}")
        print(f"Signal: {signal_obj.signal} | Confidence: {signal_obj.confidence:.0%}")
        
        # Execute
        if signal_obj.signal == "BUY":
            self.execute_trade(signal_obj, "BUY")
        elif signal_obj.signal == "SELL":
            self.execute_trade(signal_obj, "SELL")
    
    def execute_trade(self, signal_obj, direction):
        """Execute trade with stops/targets."""
        
        # Skip low confidence
        if signal_obj.confidence < 0.70:
            print("Confidence too low, skipping")
            return
        
        # Position size based on confidence
        base_size = 1.0
        size = base_size * signal_obj.confidence
        
        # Place order
        order = self.broker.place_order(
            direction=direction,
            size=size,
            entry=signal_obj.entry_price,
            stop_loss=signal_obj.stop_loss,
            take_profit=signal_obj.take_profit,
        )
        
        # Track
        self.open_trades[order.id] = signal_obj
        
        print(f"✓ Order placed: {direction} {size:.2f} @ {signal_obj.entry_price}")
```

---

## 📈 LIVE TRADING CHECKLIST

Before going live, verify:

- [ ] Backtest shows positive expectancy
- [ ] Win rate > 55%
- [ ] Circuit breaker implemented (5 loss stop)
- [ ] Position sizing formula working
- [ ] Stops are tight enough
- [ ] Targets are realistic
- [ ] Regime detection makes sense
- [ ] You understand why each trade works
- [ ] Risk management in place (1% per trade)

---

## 🚨 WHEN THINGS GO WRONG

### Signal Looks Wrong?

```python
# Add debugging
signal = manager.get_signal(df)

# Check regime
print(f"Regime: {signal.regime}")
print(f"  - Trend strength: {MarketRegimeDetector.classify(df)['trend_strength']}")
print(f"  - Volatility: {MarketRegimeDetector.classify(df)['volatility_state']}")

# Check filters
print(f"Filters passed: {strategy.passes_quality_filters(df)}")

# Check which strategy
print(f"Strategy: {manager.last_selected}")
```

### Win Rate Different Than Expected?

```python
# Backtest again on recent data
results = backtester.backtest(df, start_date="2024-01-01", end_date="2024-02-01")
backtester.print_results(results)

# Compare to projection:
# Mean Reversion should be 60%, got 50%? Problem.
# Trend Pullback should be 64%, got 70%? Lucky.
```

### Strategy Stopped Generating Signals?

```python
# Check if market went out of regime
regime = MarketRegimeDetector.classify(df)
if regime['regime'] == 'UNKNOWN':
    print("Regime detector might be broken")

# Check if all filters passing
if not strategy.passes_quality_filters(df):
    print("Filters too strict")

# Check data feed
if len(df) < 200:
    print("Not enough data for indicators")
```

---

## 📚 KEY FILES REFERENCE

| File | Purpose | Usage |
|------|---------|-------|
| `strategy_edge.py` | All 3 strategies | `from strategy_edge import EdgeStrategyManager` |
| `strategy_validation.py` | Backtesting | `from strategy_validation import StrategyBacktester` |
| `indicators.py` | Technical indicators | Used internally by strategies |
| `backtest.py` | Simulation engine | Works with strategies |
| `risk.py` | Risk management | Circuit breaker already implemented |

---

## 🎯 3-STEP DEPLOYMENT

### Step 1: Validate (Today)
```bash
python strategy_validation.py
```
Check metrics match projections.

### Step 2: Paper Trade (This Week)
```python
manager = EdgeStrategyManager()
signal = manager.get_signal(df)
# Use signal in paper trading account
```
Run through 20-30 trades.

### Step 3: Go Live (Next Week)
```python
# Deploy with circuit breaker
account_size = 1000
consecutive_losses = 0
# ... same code as paper,
#     but track consecutive losses
```
Start with small size.

---

## 💡 QUICK TIPS

1. **Use confidence for position sizing**
   - High confidence (0.85) → Full size
   - Low confidence (0.65) → Reduced size

2. **Filter by volume confirmation**
   - If `volume_confirm == False`, maybe skip
   - Volume confirms move is real

3. **Monitor regime switches**
   - When regime changes, strategy changes
   - Expect different win rate per regime

4. **Trust the stop losses**
   - Don't move stops (predefined risk)
   - Tight stops = defined risk

5. **Remember the expectancy**
   - +0.65% per trade on average
   - +65% over 100 trades
   - Don't expect every trade to win

---

## 🚀 NOW WHAT?

1. **Run validation backtest**
   ```python
   from strategy_validation import StrategyBacktester
   backtester = StrategyBacktester()
   results = backtester.backtest(df)
   backtester.print_results(results)
   ```

2. **Review results** (5 min)
   - Do metrics match projections?
   - Is regime detection correct?

3. **Paper trade** (3-5 days)
   - Generate 20-30 signals
   - Verify they make sense
   - Check regime switching

4. **Go live small** ($500-1,000)
   - Run for 1-2 weeks
   - Compare to backtest
   - Scale if tracking

5. **Grow gradually** (Weekly)
   - +2x size each week if profitable
   - -50% size if losing

---

## 📞 SUPPORT

If something doesn't work:

1. Check regime detection
   ```python
   regime = MarketRegimeDetector.classify(df)
   print(regime)
   ```

2. Check filters
   ```python
   strategy = VolatilityMeanReversionStrategy()
   print(strategy.passes_quality_filters(df))
   ```

3. Check data quality
   ```python
   print(f"Bars: {len(df)}")
   print(f"Date range: {df.index[0]} to {df.index[-1]}")
   ```

4. Read error messages carefully
   - Code is designed to be self-documenting
   - `reason` field explains why signal generated

---

## 🎓 LEARN MORE

- **STRATEGY_EDGE_GUIDE.md** - Deep dive into each strategy
- **STRATEGY_DEPLOYMENT_GUIDE.md** - Integration and deployment
- **STRATEGY_PHASE3_SUMMARY.md** - Overall summary and checklist

---

**You're ready. Let's make money! 💰**
