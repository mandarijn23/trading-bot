# 📋 Project Overview

Complete modern trading bot with AI learning, supporting both crypto and stocks.

---

## 🎯 What This Bot Does

1. **Analyzes market data** - Calculates RSI, moving averages
2. **Makes trading decisions** - Entry/exit signals with AI confidence
3. **Manages risk** - Stops losses at 2%, takes profits at 3%
4. **Learns from outcomes** - AI improves after each trade
5. **Adapts position size** - Bets more when winning, less when struggling

---

## 📁 Project Structure

```
trading-bot/
│
├── 📱 Core Trading Bots
│   ├── bot.py                 # Crypto bot (Binance, BTC/ETH/SOL)
│   ├── stock_bot.py           # Stock bot (Alpaca, SPY/QQQ/VOO)
│   └── strategy.py            # Shared RSI strategy
│
├── ⚙️ Configuration
│   ├── config.py              # Crypto config (Binance settings)
│   ├── stock_config.py        # Stock config (Alpaca settings)
│   ├── .env.example           # Template for secrets
│   └── requirements.txt       # Python dependencies
│
├── 🤖 AI/ML System
│   ├── ml_model.py            # Neural network + position sizing
│   └── ai_manage.py           # CLI: train/stats/reset
│
├── 🧪 Testing & Analysis
│   ├── backtest.py            # Historical backtesting
│   ├── test_config.py         # Unit tests for config
│   ├── test_strategy.py       # Unit tests for RSI strategy
│   └── test_ml_model.py       # Unit tests for AI
│
├── 🛠️ Setup & Deployment
│   ├── trade.py               # Interactive menu launcher
│   ├── setup_stocks.py        # Alpaca setup wizard
│   └── validate_setup.py      # Verify setup is correct
│
├── 📚 Documentation
│   ├── GET_STARTED.md         # ← Start here!
│   ├── README.md              # Project overview
│   ├── STOCK_README.md        # Stock bot quick guide
│   ├── STOCK_QUICKSTART.md    # Detailed stock setup
│   ├── START_HERE_STOCKS.md   # Crypto vs Stocks
│   ├── AI_QUICKSTART.md       # AI system explained
│   └── PROJECT_OVERVIEW.md    # This file
│
├── 📊 Generated Files (created by bot)
│   ├── .env                   # Live API keys (NEVER commit!)
│   ├── trading_model.h5       # AI neural network weights
│   ├── ai_metrics.json        # AI performance stats
│   ├── bot.log                # Crypto trading logs
│   └── stock_bot.log          # Stock trading logs
│
└── 📋 Config Files
    ├── .gitignore             # Hide secrets from git
    └── pytest.ini             # Test configuration
```

---

## 🔄 Data Flow

### Stock Trading Flow

```
Alpaca API
    ↓
stock_bot.py (fetches 100 bars)
    ↓
stock_config.py (validates settings)
    ↓
strategy.py (calculates RSI)
    ↓
ml_model.py (AI predicts confidence 0-100%)
    ↓
Decision: BUY signal + AI >45% confidence?
    ↓
place_order() → Alpaca API
    ↓
Update position + Log trade
    ↓
Later: Trade closes
    ↓
ml_model.py learns from outcome
    ↓
Position size adjusts for next trade
```

### Crypto Trading Flow (Same Pattern)

```
Binance API
    ↓
bot.py (fetches OHLCV data)
    ↓
config.py (validates settings)
    ↓
strategy.py (calculates RSI)
    ↓
ml_model.py (AI predicts confidence)
    ↓
Decision: BUY signal + AI >45% confidence?
    ↓
place_order() → Binance API
    ↓
Update position + Log trade
```

---

## 🧠 AI System Architecture

### Feature Extraction (6 indicators)

The AI looks at:

| Feature | What it means | Range |
|---------|------------|-------|
| Price change % | Is price going up? | 0 to 1 |
| Volatility | How jumpy is price? | 0 to 1 |
| Momentum | How fast trend? | 0 to 1 |
| Volume ratio | More volume than average? | 0 to 1 |
| RSI | Mean reversion signal | 0 to 1 |
| Price vs MA | Price above/below 200 MA | 0 to 1 |

### Neural Network Architecture

```
Input (6 features)
    ↓
Dense(32) + ReLU
    ↓
Dropout(0.3)
    ↓
Dense(16) + ReLU
    ↓
Dropout(0.3)
    ↓
Dense(8) + ReLU
    ↓
Dense(1) + Sigmoid
    ↓
Output: Probability 0.0 to 1.0
```

### Learning System

**Supervised Learning:**
- Train on 2000 historical candles
- Learn which patterns preceded wins

**Reinforcement Learning:**
- After each trade closes
- If won: Increase confidence for similar patterns
- If lost: Decrease confidence for similar patterns

**Position Sizing:**
- Win rate < 40%: Scale position 0.5x (play small)
- Win rate 40-60%: Scale position 1.0x (normal)
- Win rate > 60%: Scale position 1.5x (bet more)

---

## 🔐 Configuration System

### Environment Variables (.env)

```bash
# Stock Trading (Alpaca)
ALPACA_API_KEY=pk_...
ALPACA_API_SECRET=...
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# Crypto Trading (Binance)
BINANCE_API_KEY=...
BINANCE_API_SECRET=...

# Optional
LOG_LEVEL=INFO
```

### Config Files (Pydantic Validation)

**stock_config.py** (Alpaca settings):
- API credentials
- Symbols: [SPY, QQQ, VOO]
- Timeframe: 5min (adjustable)
- Trade amount: $20 per trade
- RSI bounds: oversold=35, overbought=65

**config.py** (Binance settings):
- API credentials
- Symbols: [BTC/USDT, ETH/USDT, SOL/USDT]
- Timeframe: 5m (adjustable)
- Stop loss: 2%
- Profit target: 3%

---

## 🚀 Execution Paths

### Path 1: Interactive Menu (Easiest)

```bash
python trade.py
→ Choose bot type
→ Choose action (trade/backtest/stats)
→ Run!
```

### Path 2: Direct Command

```bash
# Stock trading
python stock_bot.py

# Crypto trading
python bot.py

# Backtest
python backtest.py --compare-ai

# AI management
python ai_manage.py stats
```

### Path 3: Setup & Validate

```bash
# First time setup
python setup_stocks.py

# Verify everything
python validate_setup.py
```

---

## 📊 Key Files Explained

### Core Logic Files

**strategy.py** (70 lines)
- Pure RSI + 200MA strategy
- No side effects, fully testable
- Functions: `calculate_rsi()`, `get_signal()`

**ml_model.py** (400 lines)
- `FeatureExtractor`: 6-feature calculation
- `TradingAI`: Neural network + persistence
- `build_model()`: Creates Keras Sequential model
- `predict_entry_probability()`: Returns 0-1 score
- `update_from_trade()`: Reinforcement learning
- `get_position_size_multiplier()`: Win-rate based scaling

**bot.py** (350 lines, Crypto)
- `AsyncTradingBot`: Main trading class
- `Position`: Tracks entry time, exit price, AI confidence
- Concurrent symbol processing
- Position management (entry/exit)

**stock_bot.py** (350 lines, Stocks)
- `StockTradingBot`: Alpaca-specific version
- `StockPosition`: Quantity tracking (shares vs. base units)
- Same strategy logic as crypto bot
- REST API client instead of WebSocket

### Configuration Files

**config.py** (100 lines)
- `TradingConfig` Pydantic model with validators
- Loads from environment variables
- Type-safe config access

**stock_config.py** (100 lines)
- `StockTradingConfig` Pydantic model
- Alpaca-specific settings
- Same validation pattern as crypto

### Testing Files

**test_strategy.py**
- Tests RSI calculation
- Tests BUY/HOLD signals
- Edge case validation

**test_config.py**
- Tests config loading
- Tests validation rules
- Tests environment variable handling

**test_ml_model.py**
- Tests feature extraction
- Tests model building
- Tests prediction output range
- Tests position sizing logic

### Setup & Validation

**setup_stocks.py** (180 lines)
- Interactive setup wizard
- Prompts for API keys
- Creates .env file
- Tests connection
- Shows balance

**validate_setup.py** (150 lines)
- Checks .env file exists
- Checks dependencies installed
- Tests Alpaca connection
- Provides fix suggestions

---

## 🔄 Trade Lifecycle

### Entry
1. Bot fetches latest candles
2. Calculates RSI
3. AI predicts entry confidence
4. If RSI signals BUY AND AI >45% confident:
   - Calculate position size (1x base or scaled)
   - Place market order
   - Track entry time & price
   - Log trade

### Management
- Check stop loss: If price drops 2%, sell
- Check profit target: If price rises 3%, sell
- Log all position updates

### Exit
- Market order to close position
- Calculate P&L
- AI learns outcome (win/loss)
- Update win rate statistics
- Adjust future position sizing

### Cooldown
- After loss: Skip next signal
- Prevents revenge trading
- Recovers confidence gradually

---

## 📈 Performance Metrics

The AI tracks:

- **Total trades**: Cumulative count
- **Wins**: Number of profitable trades
- **Losses**: Number of losing trades
- **Win rate**: Wins / (Wins + Losses)
- **Total P&L**: Sum of all profits/losses
- **Position multiplier**: Current scale (0.5x - 1.5x)

Saved in `ai_metrics.json`:

```json
{
  "total_trades": 47,
  "wins": 35,
  "losses": 12,
  "win_rate": 0.744,
  "total_pnl": 42.50,
  "position_multiplier": 1.2
}
```

---

## 🧪 Testing

### Unit Tests (45+ total)

```bash
pytest test_strategy.py       # RSI strategy tests
pytest test_config.py         # Config validation tests
pytest test_ml_model.py       # AI/ML tests
pytest                        # Run all tests
```

### Integration: Backtest

```bash
python backtest.py            # Compare vs historical
python backtest.py --ai-enhanced    # With AI filter
python backtest.py --compare-ai     # Side-by-side
```

---

## 🔐 Security

- ✅ API keys ONLY in .env (never hardcoded)
- ✅ .env in .gitignore (never committed)
- ✅ Paper trading by default (no real risk)
- ✅ Type hints catch many bugs early
- ✅ Unit tests validate logic
- ✅ Config validation via Pydantic
- ✅ Comprehensive logging for audit trail

---

## 📞 Navigation

**New to the bot?** Start here:
- [GET_STARTED.md](GET_STARTED.md) - Quick setup

**Want details on stocks?**
- [STOCK_QUICKSTART.md](STOCK_QUICKSTART.md) - Step-by-step setup
- [STOCK_README.md](STOCK_README.md) - Commands & FAQ

**Want to understand the AI?**
- [AI_QUICKSTART.md](AI_QUICKSTART.md) - How it works

**Choosing between crypto & stocks?**
- [START_HERE_STOCKS.md](START_HERE_STOCKS.md) - Comparison

**Understanding the project?**
- [README.md](README.md) - Original overview
- [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) - This file

---

## 🎓 Key Concepts

### RSI (Relative Strength Index)
- Oscillates 0-100
- <30 = Oversold (buy signal)
- >70 = Overbought (sell signal)
- 200 MA filter = trend confirmation

### Position Sizing
- Base: 1.0x (normal)
- Scales: 0.5x (losing) to 1.5x (winning)
- Adapts based on AI win rate

### Confidence Score
- 0.0 = Certain loss
- 0.45 = Entry threshold
- 0.5 = No opinion
- 1.0 = Certain win

### Profit Taking
- Stop loss: -2% (risk management)
- Profit target: +3% (risk/reward 1:1.5)

---

## ✨ Next Steps

1. **Setup**: Run `python setup_stocks.py` (stocks) or add .env (crypto)
2. **Validate**: Run `python validate_setup.py`
3. **Trade**: Run `python trade.py` or `python stock_bot.py`
4. **Monitor**: Watch `stock_bot.log` or check `python ai_manage.py stats`
5. **Backtest**: Test changes with `python backtest.py`

---

**Ready to start?** See [GET_STARTED.md](GET_STARTED.md) 🚀
