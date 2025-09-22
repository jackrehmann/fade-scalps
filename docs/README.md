# Unified Fade Trading System

**One core engine. Live trading and backtesting with identical logic.**

Simple, robust fade trading system that executes inverse positions based on recent price movements. The same `FadeEngine` processes both live and historical data - no code duplication.

## 🎯 Strategy Overview

**Fade Trading Logic (All Parameters Adjustable):**
- Monitor stock prices over rolling time windows (default: 2 minutes)
- When price moves exceed threshold (default: $1.50), take inverse position
- Position size scales with magnitude of move (default: 100 shares per $1 excess)
- Built-in risk management with position limits (default: 5000 shares)

**Example:**
- TSLA up $2.50 in 2min, threshold is $1.50 → Excess = $1.00 → **Short 100 shares**
- AAPL down $3.00 in 2min → Excess = $1.50 → **Buy 150 shares**

## 🚀 Quick Start

### Prerequisites
```bash
pip install ibapi
# Ensure IBKR Gateway is running (port 4001 for paper, 4000 for live)
```

### Simple Backtesting
```python
from backtest import backtest_fade

# Test TSLA on September 12th, 2025 from 9:30-10:30 AM
result = backtest_fade("TSLA", "20250912", "09:30", "10:30")

# Test with custom parameters
result = backtest_fade(
    "TSLA", "20250912", "09:30", "10:30",
    shares_per_dollar=50,
    min_move_threshold=1.0
)

print(f"P&L: ${result.total_pnl:.2f}")
print(f"Trades: {result.total_trades}")
print(f"Win Rate: {result.win_rate:.1%}")
```

### Live Trading
```python
from live_trader import run_live_fade

# Paper trading (recommended for testing)
run_live_fade(["TSLA", "AAPL"], paper_trading=True)

# Live trading (real money)
run_live_fade(["TSLA"], paper_trading=False,
              shares_per_dollar=50,
              min_move_threshold=2.0)
```

### Parameter Optimization
```python
from multi_test import find_best_config, compare_configs

# Find optimal parameters for TSLA
best_config = find_best_config("TSLA", "20250912", "09:30", "10:30")

# Compare different configurations
configs = [
    {"shares_per_dollar": 50, "min_move_threshold": 1.0},
    {"shares_per_dollar": 100, "min_move_threshold": 1.5},
    {"shares_per_dollar": 200, "min_move_threshold": 2.0}
]
results = compare_configs("TSLA", "20250912", "09:30", "10:30", configs)
```

## 📁 Project Structure

```
fade-scalps/
├── fade_trader.py          # Core engine (used by all modules)
├── backtest.py             # Historical backtesting
├── live_trader.py          # Live trading
├── multi_test.py           # Parameter optimization
├── config.json             # Default configuration
├── README.md               # This file
└── fade_engine/
    └── ibapi_clean/        # IBKR API installation
```

## 🔧 Configuration Parameters

**All parameters are fully adjustable** - customize via config.json, command line args, or function parameters:

| Parameter | Description | Default | Adjustable Via |
|-----------|-------------|---------|----------------|
| `shares_per_dollar` | Position size per $1 of excess move | `100` | ✅ All methods |
| `min_move_threshold` | Minimum $ move to trigger trade | `$1.50` | ✅ All methods |
| `time_window_minutes` | Rolling window for price moves | `2.0` min | ✅ All methods |
| `max_position` | Maximum shares per symbol | `5000` | ✅ All methods |

### Parameter Adjustment Methods:
- **config.json** - Set system defaults
- **Command line** - `--min-move-thresh 2.5 --shares-per-dollar 50`
- **Function calls** - Pass as parameters to backtest/live functions
- **Optimization tools** - Automatic parameter sweeps to find optimal values

## 🎮 Usage Examples

### Basic Backtesting
```python
# Quick test
python3 backtest.py

# Custom backtest
from backtest import backtest_fade
result = backtest_fade("AAPL", "20250912", "09:30", "11:00",
                      shares_per_dollar=75)
```

### Live Trading Setup
```python
# Start paper trading
python3 live_trader.py

# Or programmatically
from live_trader import run_live_fade
run_live_fade(["TSLA", "AAPL", "NVDA"],
              paper_trading=True,
              min_move_threshold=1.0)
```

### Parameter Sweeps
```python
from multi_test import ParameterOptimizer

optimizer = ParameterOptimizer()

# Test all parameter combinations
parameter_grid = {
    'shares_per_dollar': [50, 100, 150],
    'min_move_threshold': [1.0, 1.5, 2.0],
    'time_window_minutes': [1.0, 2.0, 3.0]
}

results = optimizer.parameter_sweep("TSLA", "20250912", "09:30", "10:30",
                                   parameter_grid)
# Automatically finds best configuration
```

### Multi-Symbol Testing
```python
from multi_test import ParameterOptimizer

optimizer = ParameterOptimizer()

# Test same config across multiple symbols
config = {"shares_per_dollar": 100, "min_move_threshold": 1.5}
results = optimizer.multi_symbol_test(["TSLA", "AAPL", "NVDA"],
                                     "20250912", "09:30", "10:30", config)
```

## 🎯 Key Features

### Unified Architecture
- **One FadeEngine** - Same logic for live and historical data
- **Data source agnostic** - Engine only sees `(symbol, price, timestamp)`
- **Zero code duplication** - Live trading and backtesting use identical algorithms

### Advanced Testing
- **Parameter optimization** - Automatically find best configurations
- **Multi-symbol testing** - Test strategies across multiple stocks
- **Parallel backtesting** - Run multiple tests simultaneously
- **Performance analytics** - P&L, win rate, position tracking

### Production Ready
- **Paper trading mode** - Test with real data, simulated trades
- **Risk management** - Position limits, threshold filtering
- **Real-time monitoring** - Live trade execution and status updates
- **IBKR integration** - Professional-grade market data and execution

## 📊 Backtesting Workflow

```python
# 1. Quick single test
result = backtest_fade("TSLA", "20250912", "09:30", "10:30")

# 2. Parameter optimization
best_config = find_best_config("TSLA", "20250912", "09:30", "10:30")

# 3. Multi-day validation
configs_and_dates = [
    (best_config, "20250912", "09:30", "10:30"),
    (best_config, "20250913", "09:30", "10:30"),
    (best_config, "20250916", "09:30", "10:30")
]
multi_day_results = test_multiple_days("TSLA", configs_and_dates)

# 4. Go live with validated config
run_live_fade(["TSLA"], **best_config)
```

## 🛡️ Risk Management

### Built-in Safety Features
- **Position limits** - Configurable maximum shares per symbol
- **Threshold filtering** - Ignore noise below minimum move threshold
- **Paper trading default** - Test strategies safely before risking capital
- **Connection monitoring** - Graceful handling of IBKR disconnections

### Best Practices
- **Start with paper trading** - Validate strategies before live trading
- **Backtest extensively** - Test on multiple days and symbols
- **Use conservative position sizes** - Start small, scale up gradually
- **Monitor actively** - Watch logs and positions during trading sessions

## 🔍 Performance Analysis

### Backtest Results Include:
- **P&L calculation** - Realized and unrealized gains/losses
- **Trade statistics** - Total trades, win rate, maximum position
- **Price data** - All historical ticks used in analysis
- **Trade details** - Timestamp, price, quantity, reasoning for each trade

### Live Trading Monitoring:
- **Real-time trade logging** - Every signal and execution logged
- **Position tracking** - Current holdings across all symbols
- **Daily summaries** - End-of-day performance reporting
- **Order status updates** - Execution confirmations from IBKR

## 🔧 Advanced Configuration

### Custom Fade Logic
```python
# More aggressive settings
aggressive_config = {
    "shares_per_dollar": 200,
    "min_move_threshold": 0.75,
    "time_window_minutes": 1.0,
    "max_position": 10000
}

# Conservative settings
conservative_config = {
    "shares_per_dollar": 50,
    "min_move_threshold": 2.5,
    "time_window_minutes": 5.0,
    "max_position": 2000
}
```

### Multi-Timeframe Analysis
```python
# Test different time windows
time_windows = [0.5, 1.0, 2.0, 3.0, 5.0]  # minutes
for window in time_windows:
    result = backtest_fade("TSLA", "20250912", "09:30", "10:30",
                          time_window_minutes=window)
    print(f"{window}min window: ${result.total_pnl:.2f} P&L")
```

## 🚨 Troubleshooting

### Common Issues

**"Failed to connect to IBKR"**
- Ensure IBKR Gateway is running
- Check port settings (4001=paper, 4000=live)
- Verify API connections are enabled in Gateway

**"No trades generated"**
- Lower `min_move_threshold` for more sensitivity
- Check if testing during market hours
- Verify symbol has sufficient price movement

**"Import errors"**
- Install IBKR API: `pip install ibapi`
- Check Python path and module imports

### Getting Help
- Review logs in console output
- Check IBKR Gateway connection status
- Verify market data subscriptions are active

## 💡 Integration with Existing Tools

Your existing analysis tools work seamlessly:

```python
# Use fade_analyzer.py to find good candidates
from fade_analyzer import analyze_trending_stocks
candidates = analyze_trending_stocks()

# Test each candidate
for symbol in candidates:
    result = backtest_fade(symbol, "20250912", "09:30", "10:30")
    if result.total_pnl > 100:  # Profitable
        print(f"{symbol}: Good fade candidate")

# Use agentic_trader.py for AI-powered analysis
from agentic_trader import get_trading_recommendation
recommendation = get_trading_recommendation(best_performers)
```

---

## 🎉 Key Advantages

✅ **Unified codebase** - One engine, multiple data sources
✅ **Battle-tested IBKR integration** - Professional market data and execution
✅ **Comprehensive backtesting** - Historical validation with real market data
✅ **Parameter optimization** - Systematic strategy improvement
✅ **Risk management** - Built-in safety features and position limits
✅ **Production ready** - Paper trading, live execution, real-time monitoring

**Ready to start?** Try backtesting first: `python3 backtest.py`