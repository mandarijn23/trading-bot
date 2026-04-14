# API Signatures - Actual Implementation Summary

## 1. MultiTimeframeAnalyzer
**File:** `utils/multi_timeframe.py`

### Correct Attributes/Methods:
```python
class MultiTimeframeAnalyzer:
    def __init__(self, primary_timeframes: List[str] = None, delay_bars: int = 1):
        self.primary_timeframes = primary_timeframes or ["4h", "1h", "15m"]
        self.data: Dict[str, pd.DataFrame] = {}
        self.signals: Dict[str, TimeframeSignal] = {}
        self.delay_bars = delay_bars
```

### Attributes:
- ✅ `primary_timeframes: List[str]`
- ✅ `data: Dict[str, pd.DataFrame]`
- ✅ `signals: Dict[str, TimeframeSignal]`
- ✅ `delay_bars: int`

### Methods:
- `add_timeframe_data(timeframe: str, df: pd.DataFrame) -> None`
- `analyze_single_timeframe(timeframe: str, df: pd.DataFrame, rsi_period: int = 14, ema_fast: int = 9, ema_slow: int = 21) -> TimeframeSignal`

---

## 2. ExecutionPlan
**File:** `utils/execution_optimizer.py`

### Correct Definition:
```python
@dataclass
class ExecutionPlan:
    """Details of how to execute an order optimally."""
    strategy: Literal["MARKET", "LIMIT", "TWAP", "ICEBERG"]
    price: float
    quantity: int
    total_quantity: int
    num_slices: int
    time_horizon_sec: int
    urgency: float
    expected_improvement: float
    rationale: str
```

### Attributes (ALL):
- ✅ `strategy: Literal["MARKET", "LIMIT", "TWAP", "ICEBERG"]`
- ✅ `price: float`
- ✅ `quantity: int`
- ✅ `total_quantity: int`
- ✅ `num_slices: int`
- ✅ `time_horizon_sec: int`
- ✅ `urgency: float` (0-1, how urgently needed)
- ✅ `expected_improvement: float` (% better than market)
- ✅ `rationale: str`

---

## 3. StrategySignalEnsemble
**File:** `utils/multi_strategy_engine.py`

### Correct Definition:
```python
@dataclass
class StrategySignalEnsemble:
    """Ensemble signal combining multiple strategies."""
    primary_signal: Literal["BUY", "HOLD", "SELL"]
    confidence: float  # 0-1, how many strategies agree
    strategies_voting: Dict[str, Literal["BUY", "HOLD", "SELL"]]
    weights: Dict[str, float]
    entry_price: float
    stop_loss: float
    take_profit: float
    reason: str
```

### Attributes (NOT 'signal', but 'primary_signal'):
- ✅ `primary_signal: Literal["BUY", "HOLD", "SELL"]` (NOT just 'signal')
- ✅ `confidence: float` (0-1, confidence level)
- ✅ `strategies_voting: Dict[str, Literal["BUY", "HOLD", "SELL"]]` (individual strategy votes)
- ✅ `weights: Dict[str, float]` (weight for each strategy)
- ✅ `entry_price: float`
- ✅ `stop_loss: float`
- ✅ `take_profit: float`
- ✅ `reason: str`

---

## 4. MarketRegime
**File:** `utils/macro_regime.py`

### Correct Definition:
```python
@dataclass
class MarketRegime:
    """Current market conditions."""
    regime: Literal["NORMAL", "STRESS", "DISTRESSED", "OPPORTUNITY"]
    vix_level: float
    liquidity: Literal["EXCELLENT", "GOOD", "FAIR", "POOR"]
    volatility_regime: Literal["LOW", "NORMAL", "HIGH", "EXTREME"]
    trend_clarity: float  # 0-1
    market_hour_type: Literal["OPEN", "MID_DAY", "CLOSE"]
    should_trade: bool
    trade_aggressiveness: float  # 0.2-1.5, adjust sizing
    reason: str
```

### 🔴 CRITICAL FIX:
- ❌ WRONG: `aggressiveness`
- ✅ CORRECT: `trade_aggressiveness` (NOT 'aggressiveness')

### Full Attributes:
- ✅ `regime: Literal["NORMAL", "STRESS", "DISTRESSED", "OPPORTUNITY"]`
- ✅ `vix_level: float`
- ✅ `liquidity: Literal["EXCELLENT", "GOOD", "FAIR", "POOR"]`
- ✅ `volatility_regime: Literal["LOW", "NORMAL", "HIGH", "EXTREME"]`
- ✅ `trend_clarity: float` (0-1, how clear the trend is)
- ✅ `market_hour_type: Literal["OPEN", "MID_DAY", "CLOSE"]`
- ✅ `should_trade: bool`
- ✅ `trade_aggressiveness: float` (0.2-1.5, adjust sizing)
- ✅ `reason: str`

---

## 5. MultiStrategyAllocator
**File:** `utils/capital_allocation.py`

### Correct __init__ Signature:
```python
class MultiStrategyAllocator:
    def __init__(self, rebalance_frequency: str = "daily"):
        """
        Initialize allocator.
        
        Args:
            rebalance_frequency: "daily", "weekly", or "never"
        """
        self.strategies: Dict[str, StrategyPerformance] = {}
        self.allocations: Dict[str, float] = {}
        self.rebalance_frequency = rebalance_frequency
        self.last_rebalance = None
        self.logger = logging.getLogger("allocator")
```

### __init__ Parameters:
- ✅ `rebalance_frequency: str = "daily"` (ONLY parameter)
  - Valid values: "daily", "weekly", "never"

### Methods:
- `register_strategy(name: str) -> None`
- `update_performance(strategy_name: str, trades: List[tuple]) -> None`
- `calculate_allocations() -> Dict[str, float]`
- `get_position_size_for_strategy(strategy_name: str, total_capital: float) -> float`

---

## 6. OptionsStrategyGenerator.generate_covered_call()
**File:** `utils/options_strategies.py`

### Correct Signature:
```python
def generate_covered_call(
    self,
    symbol: str,
    current_stock_price: float,
    shares_owned: int,
    call_options: List[OptionContract],  # ✅ List of OptionContract objects
    target_income_pct: float = 0.03,
) -> Optional[OptionsStrategy]:
```

### 🔴 CRITICAL FIX:
- ❌ WRONG: `call_options` as Dict
- ✅ CORRECT: `call_options: List[OptionContract]` (list of OptionContract objects)

### OptionContract Definition:
```python
@dataclass
class OptionContract:
    """Options contract details."""
    symbol: str
    expiration: str  # "YYYY-MM-DD"
    strike: float
    option_type: Literal["CALL", "PUT"]
    bid: float
    ask: float
    implied_vol: float
    days_to_expiration: int
```

### Parameters:
- ✅ `symbol: str`
- ✅ `current_stock_price: float`
- ✅ `shares_owned: int`
- ✅ `call_options: List[OptionContract]` (NOT Dict, but List)
- ✅ `target_income_pct: float = 0.03` (income target as % of stock price)

### Returns:
- `Optional[OptionsStrategy]` (None if not viable)

---

## Summary of Fixes Needed

| Item | Current (Wrong) | Correct | Type |
|------|-----------------|---------|------|
| MarketRegime.aggressiveness | `aggressiveness: float` | `trade_aggressiveness: float` | Attribute rename |
| StrategySignalEnsemble.signal | `signal: str` | `primary_signal: Literal["BUY", "HOLD", "SELL"]` | Attribute rename + type fix |
| OptionsStrategyGenerator.generate_covered_call() | `call_options: Dict` | `call_options: List[OptionContract]` | Parameter type |
| MultiStrategyAllocator.__init__() | Multiple params? | `rebalance_frequency: str = "daily"` | Confirm single param |

