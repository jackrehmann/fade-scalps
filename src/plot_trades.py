#!/usr/bin/env python3
"""
Simple plotting script for fade trading backtest results
"""

import json
import sys
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import re
from matplotlib.patches import Rectangle
import threading
import time
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract

class BarDataClient(EWrapper, EClient):
    """IBKR client to fetch 1-minute bars for plotting"""

    def __init__(self):
        EClient.__init__(self, self)
        self.bars = []
        self.finished = False

    def error(self, reqId, errorCode, errorString, *args):
        # Handle both parameter orders - sometimes errorCode and errorString are swapped
        actual_error_code = errorString if isinstance(errorString, int) else errorCode
        if actual_error_code not in [2104, 2106, 2158, 1102]:  # Skip connection status
            print(f'[BAR DATA] Error {actual_error_code}: {errorCode if isinstance(errorString, int) else errorString}')

    def historicalData(self, reqId, bar):
        """Receive 1-minute bar data"""
        # Handle timezone info in bar.date (e.g., "20250912 09:30:00 US/Eastern")
        date_str = bar.date.split(' US/Eastern')[0]  # Remove timezone part
        self.bars.append({
            'timestamp': datetime.strptime(date_str, '%Y%m%d %H:%M:%S'),
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
            'volume': bar.volume
        })

    def historicalDataEnd(self, reqId, start, end):
        """Called when bar data is complete"""
        print(f'[BAR DATA] Received {len(self.bars)} 1-minute bars')
        self.finished = True

def fetch_1min_bars(symbol: str, date: str, start_time: str, end_time: str):
    """Fetch 1-minute bars from IBKR"""
    client = BarDataClient()

    try:
        client.connect('127.0.0.1', 4002, 7777)
        thread = threading.Thread(target=client.run, daemon=True)
        thread.start()

        # Wait for connection
        time.sleep(1)

        # Create contract
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"

        # Request 1-minute bars
        end_datetime = f"{date} {end_time}:00 US/Eastern"
        duration = "1 D"  # 1 day of data (will be filtered by end time)

        client.reqHistoricalData(
            reqId=1001,
            contract=contract,
            endDateTime=end_datetime,
            durationStr=duration,
            barSizeSetting="1 min",
            whatToShow="TRADES",
            useRTH=1,
            formatDate=1,
            keepUpToDate=False,
            chartOptions=[]
        )

        # Wait for completion
        timeout = 10  # 10 second timeout
        start = time.time()
        while not client.finished and (time.time() - start) < timeout:
            time.sleep(0.1)

        client.disconnect()

        if client.bars:
            # Convert to DataFrame and filter by time range
            df = pd.DataFrame(client.bars)
            df.set_index('timestamp', inplace=True)

            # Filter to the requested time range
            start_dt = datetime.strptime(f"{date} {start_time}:00", "%Y%m%d %H:%M:%S")
            end_dt = datetime.strptime(f"{date} {end_time}:00", "%Y%m%d %H:%M:%S")

            df = df[(df.index >= start_dt) & (df.index <= end_dt)]

            return df[['open', 'high', 'low', 'close']]
        else:
            print("[BAR DATA] No bars received")
            return None

    except Exception as e:
        print(f"[BAR DATA] Error fetching bars: {e}")
        return None

def plot_candlesticks(ax, ohlc_data):
    """Plot 1-minute candlesticks"""
    for timestamp, row in ohlc_data.iterrows():
        if pd.isna(row['open']) or pd.isna(row['close']):
            continue

        open_price = row['open']
        high_price = row['high']
        low_price = row['low']
        close_price = row['close']

        # Determine color (green for up, red for down)
        color = 'green' if close_price >= open_price else 'red'
        alpha = 0.25

        # Draw the high-low line
        ax.plot([timestamp, timestamp], [low_price, high_price],
               color=color, linewidth=1, alpha=0.25)

        # Draw the open-close rectangle
        height = abs(close_price - open_price)
        bottom = min(open_price, close_price)

        # Use a thin rectangle for the body
        width = pd.Timedelta(seconds=30)  # 30-second width for visibility
        rect = Rectangle((timestamp - width/2, bottom), width, height,
                        facecolor=color, alpha=alpha, edgecolor='black', linewidth=0.5)
        ax.add_patch(rect)

def plot_backtest_trades(json_file: str):
    """
    Plot backtest trades showing price, position, and excess moves
    """
    # Load data
    with open(json_file, 'r') as f:
        data = json.load(f)

    # Handle both backtest and live trading file formats
    if 'backtest_info' in data:
        backtest_info = data['backtest_info']
    elif 'session_info' in data:
        # Convert live trading format to backtest format
        session_info = data['session_info']
        backtest_info = {
            'symbol': session_info['symbols'][0] if session_info['symbols'] else 'UNKNOWN',
            'date': session_info['date'],
            'start_time': session_info.get('start_time', '09:30'),  # Use actual start_time or default
            'end_time': session_info.get('end_time') or '16:00',    # Handle null end_time
            'total_trades': session_info.get('total_trades', 0),
            'total_pnl': 0.0,  # Will calculate from trades
            'win_rate': 0.0,   # Will calculate from trades
            'max_position': 0,  # Will calculate from trades
            'final_position': sum(session_info.get('final_positions', {}).values()),
            'session_type': session_info.get('session_type', 'live_trading')  # Add session type
        }
    else:
        raise ValueError("Invalid file format: missing 'backtest_info' or 'session_info'")

    trades = data['trades']

    if not trades:
        print("No trades found in backtest data")
        return

    # Convert to DataFrame
    df_trades = pd.DataFrame(trades)
    df_trades['timestamp'] = pd.to_datetime(df_trades['timestamp'])

    # Separate buy and sell trades
    buy_trades = df_trades[df_trades['action'] == 'BUY']
    sell_trades = df_trades[df_trades['action'] == 'SELL']

    # Fetch real 1-minute bars from IBKR for close prices
    # Handle both backtest and live trading file formats
    from datetime import datetime, timedelta

    symbol = backtest_info['symbol']
    date = backtest_info['date']

    if 'session_type' in backtest_info and backtest_info['session_type'] == 'live_trading':
        # Live trading format - determine time range from actual trades
        if len(df_trades) > 0:
            first_trade = df_trades['timestamp'].min()
            last_trade = df_trades['timestamp'].max()

            # Extract start and end times from trade timestamps
            start_dt = first_trade - timedelta(minutes=5)  # 5 min buffer
            end_dt = last_trade + timedelta(minutes=5)     # 5 min buffer
            extended_start = start_dt.strftime("%H:%M")
            extended_end = end_dt.strftime("%H:%M")
        else:
            # No trades, use reasonable default
            extended_start = "09:30"
            extended_end = "16:00"
    else:
        # Backtest format - use specified start/end times
        start_time = backtest_info['start_time']
        end_time = backtest_info['end_time']

        # Extend time window by 1 minute before and 2 minutes after for better coverage
        start_dt = datetime.strptime(start_time, "%H:%M") - timedelta(minutes=1)
        end_dt = datetime.strptime(end_time, "%H:%M") + timedelta(minutes=2)
        extended_start = start_dt.strftime("%H:%M")
        extended_end = end_dt.strftime("%H:%M")

    if 'session_type' in backtest_info and backtest_info['session_type'] == 'live_trading':
        print(f"[PLOT] Fetching 1-minute close prices for {symbol} {date} {extended_start}-{extended_end} (live trading session)")
    else:
        print(f"[PLOT] Fetching 1-minute close prices for {symbol} {date} {extended_start}-{extended_end} (extended from {start_time}-{end_time})")
    ohlc_1min = fetch_1min_bars(symbol, date, extended_start, extended_end)

    if ohlc_1min is not None:
        # Use the close prices from IBKR bars
        price_line = ohlc_1min['close']
    else:
        print("[PLOT] Failed to fetch 1-minute bars, falling back to trade data")
        # Fallback to trade-based price line
        price_data = df_trades[['timestamp', 'price']].copy()
        price_data = price_data.sort_values('timestamp')
        price_data.set_index('timestamp', inplace=True)
        price_line = price_data['price'].resample('1T').mean().fillna(method='ffill')

    # Set up the plot with shared x-axis (add 4th subplot for cumulative P&L)
    fig, (ax1, ax2, ax3, ax4) = plt.subplots(4, 1, figsize=(15, 20), height_ratios=[3, 1, 1, 1], sharex=True)

    # Plot 1-minute candlesticks (if OHLC data available) or line (fallback)
    if ohlc_1min is not None:
        plot_candlesticks(ax1, ohlc_1min)
    else:
        ax1.plot(price_line.index, price_line.values, color='blue', linewidth=1, alpha=0.7, label='1-min Close')

    # Track position to determine sell context
    position = 0
    sell_long_trades = []
    sell_short_trades = []

    for _, trade in df_trades.iterrows():
        if trade['action'] == 'SELL':
            if position > 0:  # Selling from long position
                sell_long_trades.append(trade)
            else:  # Selling short (going more negative)
                sell_short_trades.append(trade)
            position -= trade['quantity']
        else:  # BUY
            position += trade['quantity']

    # Plot trade markers with position context
    if sell_long_trades:
        sell_long_df = pd.DataFrame(sell_long_trades)
        ax1.scatter(sell_long_df['timestamp'], sell_long_df['price'],
                   color='red', marker='v', s=30, alpha=0.7, label='SELL Long')

    if sell_short_trades:
        sell_short_df = pd.DataFrame(sell_short_trades)
        ax1.scatter(sell_short_df['timestamp'], sell_short_df['price'],
                   color='hotpink', marker='v', s=30, alpha=0.7, label='SELL Short')

    if not buy_trades.empty:
        ax1.scatter(buy_trades['timestamp'], buy_trades['price'],
                   color='green', marker='^', s=30, alpha=0.7, label='BUY')

    # Simple legend (no candlestick patches needed)

    # Formatting
    ax1.set_title(f'{backtest_info["symbol"]} Fade Trading - {backtest_info["date"]} {backtest_info["start_time"]}-{backtest_info["end_time"]}')
    ax1.set_ylabel('Price ($)', fontsize=12)
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # Format x-axis (only for bottom subplot since sharex=True)
    ax4.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    ax4.xaxis.set_major_locator(mdates.MinuteLocator(interval=1))
    plt.setp(ax4.xaxis.get_majorticklabels(), rotation=45)

    # Position tracking subplot
    position = 0
    positions = []
    position_times = []

    for _, trade in df_trades.iterrows():
        if trade['action'] == 'BUY':
            position += trade['quantity']
        else:  # SELL
            position -= trade['quantity']

        positions.append(position)
        position_times.append(trade['timestamp'])

    if positions:
        # Create step bars that fill forward until next position change
        for i in range(len(positions)):
            start_time = position_times[i]
            position = positions[i]

            # Determine end time (next trade time or extend to chart end)
            if i < len(positions) - 1:
                end_time = position_times[i + 1]
            else:
                # For the last position, extend to session end time
                session_end = datetime.strptime(f"{backtest_info['date']} {backtest_info['end_time']}:00", "%Y%m%d %H:%M:%S")
                end_time = pd.Timestamp(session_end)
                # If last trade is after session end, just extend a minute
                if start_time >= end_time:
                    end_time = start_time + pd.Timedelta(minutes=1)

            # Color based on position
            color = 'green' if position > 0 else 'red' if position < 0 else 'gray'

            # Create filled bar from start_time to end_time
            width = end_time - start_time
            ax2.bar(start_time, position, width=width, align='edge',
                   color=color, alpha=0.7, edgecolor='none')

        ax2.axhline(y=0, color='black', linestyle='--', alpha=0.5)
        ax2.set_ylabel('Position (Shares)', fontsize=12)
        ax2.grid(True, alpha=0.3)

        # X-axis formatting handled by shared axis

    # Excess Move subplot
    excess_times = []
    excess_moves = []

    for _, trade in df_trades.iterrows():
        if 'excess: $' in trade['reason']:
            try:
                # Parse excess move from reason string
                match = re.search(r'excess: \$([0-9.-]+)', trade['reason'])
                if match:
                    excess_move = float(match.group(1))
                    excess_times.append(trade['timestamp'])
                    excess_moves.append(excess_move)
            except (ValueError, IndexError):
                # Skip if parsing fails
                continue

    if excess_moves:
        # Plot excess moves as scatter plot with color coding
        # Get corresponding actions for trades with excess moves
        trade_actions = []
        for _, trade in df_trades.iterrows():
            if 'excess: $' in trade['reason']:
                trade_actions.append(trade['action'])

        colors = ['red' if action == 'SELL' else 'green' for action in trade_actions]
        ax3.scatter(excess_times, excess_moves, c=colors, alpha=0.6, s=20)
        ax3.axhline(y=0, color='black', linestyle='--', alpha=0.5)
        ax3.set_ylabel('Excess Move ($)', fontsize=12)
        ax3.grid(True, alpha=0.3)

    # Cumulative P&L subplot
    def _get_total_pnl(trades_subset):
        """Calculate total P&L for a subset of trades"""
        if trades_subset.empty:
            return 0.0

        final_execution = trades_subset['position_change'].sum() * trades_subset['price'].iloc[-1]
        pre_execution = (trades_subset['position_change'] * trades_subset['price'] * -1).sum()
        pnl = pre_execution + final_execution
        return pnl

    # Add position_change column to df_trades
    df_trades['position_change'] = df_trades['quantity'] * df_trades['action'].map({'BUY': 1, 'SELL': -1})

    # Calculate cumulative P&L
    cumulative_pnl = []
    pnl_times = []

    for i in range(len(df_trades)):
        trades_subset = df_trades.iloc[:i+1]
        pnl = _get_total_pnl(trades_subset)
        cumulative_pnl.append(pnl)
        pnl_times.append(trades_subset['timestamp'].iloc[-1])

    if cumulative_pnl:
        ax4.plot(pnl_times, cumulative_pnl, color='purple', linewidth=2, label='Cumulative P&L')
        ax4.axhline(y=0, color='black', linestyle='--', alpha=0.5)
        ax4.set_ylabel('Cumulative P&L ($)', fontsize=12)
        ax4.set_xlabel('Time', fontsize=12)
        ax4.grid(True, alpha=0.3)

        # Color the area under the curve
        ax4.fill_between(pnl_times, cumulative_pnl, 0, alpha=0.3,
                        color='green' if cumulative_pnl[-1] >= 0 else 'red')

    # Add statistics text
    stats_text = f"""Statistics:
Total Trades: {backtest_info['total_trades']}
P&L: ${backtest_info['total_pnl']:.2f}
Win Rate: {backtest_info['win_rate']:.1%}
Max Position: {backtest_info['max_position']} shares
Final Position: {backtest_info['final_position']} shares"""

    # Add text box with statistics
    fig.text(0.02, 0.98, stats_text, fontsize=10, verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.8))

    # Adjust layout
    plt.tight_layout()
    plt.subplots_adjust(left=0.15)  # Make room for stats

    # Save chart
    chart_filename = json_file.replace('.json', '_chart.png')
    plt.savefig(chart_filename, dpi=300, bbox_inches='tight')
    print(f"📊 Chart saved to: {chart_filename}")

    # Close plot without showing (saves memory and prevents GUI from opening)
    plt.close()

    # Print summary
    print(f"\n📈 TRADE VISUALIZATION SUMMARY")
    print(f"   File: {json_file}")
    print(f"   BUY trades: {len(buy_trades)}")
    print(f"   SELL trades: {len(sell_trades)}")
    if not df_trades.empty:
        print(f"   Time span: {df_trades['timestamp'].min().strftime('%H:%M:%S')} to {df_trades['timestamp'].max().strftime('%H:%M:%S')}")
        print(f"   Price range: ${df_trades['price'].min():.2f} - ${df_trades['price'].max():.2f}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python plot_trades.py <backtest_json_file>")
        sys.exit(1)

    json_file = sys.argv[1]
    print(f"Plotting: {json_file}")
    plot_backtest_trades(json_file)