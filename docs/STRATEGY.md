# Fade Trading Strategy Documentation

## Overview

This is a mean-reversion (fade) trading strategy that takes contrarian positions when price moves exceed a specified threshold, expecting prices to revert back toward their recent average.

## Core Concept

The strategy "fades" large price movements by:
- **Going LONG** when price falls significantly (expecting bounce back up)
- **Going SHORT** when price rises significantly (expecting pullback down)

## Key Parameters

| Parameter | Description | Current Default |
|-----------|-------------|-----------------|
| `shares_per_dollar` | Number of shares to trade per $1 of excess move | 100 |
| `min_move_threshold` | Minimum price move required to trigger trades | $2.50 |
| `time_window_minutes` | Rolling window for calculating price range | 2.0 minutes |
| `max_position` | Maximum position size limit | 5000 shares |

## Strategy Logic

### 1. Price Movement Calculation

For each tick, the system calculates:
- **Window High**: Highest price in the last 2 minutes
- **Window Low**: Lowest price in the last 2 minutes
- **Price Move**: Distance from current price to the furthest extreme:
  - `move_from_high = window_high - current_price` (negative = down from high)
  - `move_from_low = current_price - window_low` (positive = up from low)
  - **Final move** = larger absolute value with appropriate sign

### 2. Position Sizing

When `|price_move| >= $2.50`:
- **Excess Move** = `|price_move| - $2.50`
- **Goal Position Size** = `excess_move × 100 shares`
- **Direction**: Opposite to the move (fade/contrarian)

### 3. Unified Move Calculation

The strategy uses a unified "move" concept that adapts based on current position:

#### Position-Aware Move Calculation
- **If Flat**: `move = price_move` (standard window-based move)
- **If Long**: `move = current_price - window_high` (negative when below high)
- **If Short**: `move = current_price - window_low` (positive when above low)

This creates consistent move signs across all position states.

#### Action-Based Decision Logic

**Expansion**: `if |move| >= threshold`
- Available to flat positions or when position is losing to current move
- Direction: Fade the move (opposite direction)
- Size: `(|move| - threshold) × shares_per_dollar`
- Peak tracking: Updates peak position on expansion

**Contraction**: `if |move| < threshold AND positioned`
- Only reduces existing positions, never expands
- Scaling: `goal = peak_position × (|move| / threshold)`
- Constraint: Goal position cannot exceed current position size
- Elimination: Positions below 10 shares are zeroed out

**Hold**: All other cases
- Maintains current position when no clear expansion or contraction signal

### 4. Improved Profit-Taking

**Key Fix**: The previous system would get "stuck" in large positions when moves stayed above threshold. The new logic takes profits whenever price moves favorably, regardless of threshold.

**Benefits:**
- Responsive to window contraction (tight range = reduce positions)
- Takes profits on favorable price movement
- Prevents holding large positions through complete reversals
- Symmetric logic for long and short positions

## Example Trade Sequence

**Previous Behavior (Problematic):**
```
Time    Price   Move    Action           Position    Reason
09:30   $420   -$2.60   BUY 10 shares    +10        Fade down move (excess: $0.10)
09:31   $419   -$3.60   BUY 100 shares   +110       Expand position (excess: $1.10)
09:32   $421   -$2.60   HOLD             +110       Stuck! Move still > threshold
09:33   $422   -$1.60   SELL 46 shares   +64        Finally scale down below threshold
```

**New Behavior (Improved):**
```
Time    Price   Move    Action           Position    Reason
09:30   $420   -$2.60   BUY 10 shares    +10        Fade down move (excess: $0.10)
09:31   $419   -$3.60   BUY 100 shares   +110       Expand position (excess: $1.10)
09:32   $421   -$1.00   SELL 66 shares   +44        Take profits! (favorable move)
09:33   $422   -$0.50   SELL 22 shares   +22        Continue scaling down
09:34   $422.50 $0.00   SELL 22 shares   0          Flatten position
```

## Risk Management Features

### 1. Maximum Position Limits
- Hard cap at 5000 shares to prevent runaway positions
- Position size scales with move magnitude, not time

### 2. Automatic Flattening
- All positions are automatically closed at end of trading session
- Ensures clean daily P&L calculation

### 3. Rolling Window Cleanup
- Price data older than 2 minutes is automatically removed
- Prevents stale data from affecting calculations

### 4. Position Continuity
- No jarring position flips from long to short
- Smooth scaling ensures controlled risk exposure

## P&L Calculation

The system uses **mark-to-market** P&L calculation:
- **Long trades**: `quantity × (final_price - entry_price)`
- **Short trades**: `quantity × (entry_price - final_price)`
- **Total P&L**: Sum of all individual trade P&Ls marked to final session price

## Technical Implementation

### Key Components
- **FadeEngine**: Core strategy logic and position management
- **PriceHistory**: Rolling window price tracking with timestamp management
- **Backtest System**: Historical data replay with IBKR integration
- **Position-Aware Logic**: Prevents premature exits and jarring flips

### Data Requirements
- High-frequency tick data (bid/ask from IBKR)
- Precise timestamp handling for rolling window accuracy
- Real-time position tracking and peak position memory

## Current Performance Characteristics

Based on recent backtests:
- **Entry Frequency**: Moderate (trades only on significant moves ≥$2.50)
- **Hold Duration**: Variable (seconds to minutes based on mean reversion speed)
- **Win Rate**: Typically 15-35% (many small losses, fewer large wins)
- **Risk Profile**: Controlled through position scaling and maximum limits

## Strategy Strengths

1. **Systematic Mean Reversion**: Exploits natural price reversion tendencies
2. **Position Scaling**: Larger moves = larger positions (conviction-based sizing)
3. **Risk Control**: Multiple safeguards prevent runaway losses
4. **Smooth Transitions**: Avoids whipsaw from rapid position changes

## Strategy Limitations

1. **Trending Markets**: Can accumulate losses during sustained trends
2. **Gap Risk**: Large overnight gaps can cause significant losses
3. **Commission Sensitivity**: High trade frequency increases transaction costs
4. **Parameter Sensitivity**: Performance depends on optimal threshold and window settings

## Future Enhancements

Potential improvements to consider:
- Dynamic threshold adjustment based on volatility
- Multiple timeframe analysis (e.g., 1min + 5min windows)
- Volume-weighted position sizing
- Volatility-based position limits
- Stop-loss mechanisms for extreme moves