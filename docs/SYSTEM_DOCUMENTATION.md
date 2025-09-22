# Fade Trading System - Complete Documentation

## Overview

This is a mean-reversion (fade) trading strategy that takes contrarian positions when price moves exceed a specified threshold, expecting prices to revert back toward their recent average.

## System Architecture

### Core Components

1. **FadeEngine** (`fade_engine.py`) - Core strategy logic and position management
2. **Live Trader** (`fade_trader.py`) - Real-time trading with IBKR integration
3. **Backtest System** (`backtest.py`) - Historical data replay with IBKR integration
4. **Plotting Tool** (`plot_trades.py`) - Trade visualization with 1-minute bars

### Configuration

- **Config File**: `config.json` - Contains strategy parameters and IBKR connection settings
- **Environment**: `.env` - API keys (NEVER commit to git)

## Strategy Logic

### Core Concept
- **Go LONG** when price falls significantly (expecting bounce back up)
- **Go SHORT** when price rises significantly (expecting pullback down)

### Key Parameters
- `shares_per_dollar`: Number of shares to trade per $1 of excess move (default: 100)
- `min_move_threshold`: Minimum price move required to trigger trades (default: $2.50)
- `time_window_minutes`: Rolling window for calculating price range (default: 2.0 minutes)
- `max_position`: Maximum position size limit (default: 5000 shares)

### Price Movement Calculation
1. **Window High**: Highest price in the rolling time window
2. **Window Low**: Lowest price in the rolling time window
3. **Price Move**: Distance from current price to furthest extreme
4. **Excess Move**: `|price_move| - min_move_threshold`
5. **Position Size**: `excess_move × shares_per_dollar`

### Asymmetric Ratchet System
- **Above Threshold**: Can only expand position size, never reduce
- **Below Threshold**: Can only reduce position size (if positioned) or stay flat

## IBKR Integration

### Critical Lessons Learned

#### Data Source Priority
**ALWAYS use bid/ask midpoint, not just LAST price**
```python
# WRONG - only reacts to LAST trades (sparse)
if tickType == 4:  # LAST only

# RIGHT - uses bid/ask midpoint (frequent updates)
if tickType == 1:   # BID
    mid = 0.5 * (bid + ask)
elif tickType == 2: # ASK
    mid = 0.5 * (bid + ask)
```

#### Connection Settings
- **Live Trading**: Port 4001
- **Paper Trading**: Port 4002
- **Always call**: `reqIds(-1)` and `reqMarketDataType(1)` after connection
- **Contract Specification**: Include `primaryExchange` (e.g., "NASDAQ" for TSLA)

#### Error Handling
```python
# Filter noisy status messages but log all real errors
noisy_status = {2104, 2106, 2158, 1102}
if errorCode not in noisy_status:
    logger.error(f"[reqId={reqId}] IB Error {errorCode}: {errorString}")
```

#### Market Data Types
- 1 = LIVE
- 2 = FROZEN
- 3 = DELAYED
- 4 = DELAYED-FROZEN

### Paper Trading Limitations
- Paper trading (port 4002) sometimes has limited real-time price data
- May only receive size/volume updates without actual prices
- For testing strategy logic, connect to live port (4001) with `dry_run: true`

## Usage Examples

### Live Trading (Dry Run)
```bash
python3 fade_trader.py --symbols TSLA --min-move-thresh 2.5 --time-window 2.0 --shares-per-dollar 100 --dry-run
```

### Backtesting
```bash
python3 backtest.py TSLA 20250915 09:30 09:50 --min-move-thresh 2.5 --shares-per-dollar 100 --time-window 2.0
```

### Plotting Results
```bash
python3 plot_trades.py backtest_TSLA_20250915_0930-0950.json
```

### Testing with Small Thresholds
```bash
# Generate frequent trades for testing
python3 fade_trader.py --symbols TSLA --min-move-thresh 0.10 --time-window 0.5 --dry-run
```

## File Structure

```
fade-scalps/
├── config.json              # Strategy configuration
├── .env                     # API keys (DO NOT COMMIT)
├── .gitignore              # Git ignore file
├── fade_trader.py          # Live trading system
├── backtest.py             # Historical backtesting
├── plot_trades.py          # Trade visualization
├── fade_engine.py          # Core strategy engine
├── STRATEGY.md             # Strategy documentation
└── SYSTEM_DOCUMENTATION.md # This file
```

## Critical Implementation Details

### Bid/Ask Tracking
```python
# Keep last bid/ask per symbol for midpoint calculation
self.last_bid: Dict[str, float] = {}
self.last_ask: Dict[str, float] = {}

def tickPrice(self, reqId, tickType, price, attrib):
    if tickType == 1:   # BID
        self.last_bid[symbol] = price
        ask = self.last_ask.get(symbol)
        if ask:  # Have both sides -> use midpoint
            mid = 0.5 * (price + ask)
            signal = self.fade_engine.update_price(symbol, mid)
```

### JSON Saving Architecture
- **Backtest**: Saves JSON at end of completion in `BacktestClient._complete_backtest()`
- **Live Trader**: Saves dry run trades in `IBKRClient.save_dry_run_trades()` on disconnect
- **Robust timestamp handling**: Handles both datetime objects and ISO strings

### Position Management
- Positions tracked in `fade_engine.positions` dict
- Automatic flattening at end of backtest session
- Mark-to-market P&L calculation

## Common Issues & Solutions

### Connection Problems
- **Error 502**: Port already in use or TWS/Gateway not running
- **No price data**: Check market data subscriptions and permissions
- **Only size data**: Paper trading limitations - use live port with dry_run

### Git Issues
- **Never commit `.env`** - contains API keys
- **Use `.gitignore`** to exclude sensitive files
- **Remove secrets from history** if accidentally committed

### Performance Optimization
- Window math is O(n) per tick - consider deque-based rolling max/min for high frequency
- Position updates only on actual trades (not micro-movements)

## Testing Strategy

1. **Start with small thresholds** (0.10) and short windows (0.5 min) for rapid testing
2. **Use dry run mode** extensively before live trading
3. **Compare live vs backtest results** to verify consistency
4. **Monitor market data type** to ensure live data access

## Security Notes

- **API Keys**: Store in `.env`, never commit to git
- **Dry Run Mode**: Always test with `dry_run: true` first
- **Paper Trading**: Use port 4002 for safe testing
- **Position Limits**: Enforce `max_position` to prevent runaway trades

## Performance Characteristics

Based on backtests:
- **Entry Frequency**: Moderate (trades only on significant moves ≥threshold)
- **Hold Duration**: Variable (seconds to minutes based on mean reversion speed)
- **Win Rate**: Typically 15-35% (many small losses, fewer large wins)
- **Risk Profile**: Controlled through position scaling and maximum limits

## Future Enhancements

- Dynamic threshold adjustment based on volatility
- Multiple timeframe analysis (1min + 5min windows)
- Volume-weighted position sizing
- Stop-loss mechanisms for extreme moves
- Tick-by-tick data streams for ultra-low latency