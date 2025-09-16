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
        alpha = 0.7

        # Draw the high-low line
        ax.plot([timestamp, timestamp], [low_price, high_price],
               color='black', linewidth=1, alpha=0.8)

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

    backtest_info = data['backtest_info']
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
    symbol = backtest_info['symbol']
    date = backtest_info['date']
    start_time = backtest_info['start_time']
    end_time = backtest_info['end_time']

    print(f"[PLOT] Fetching 1-minute close prices for {symbol} {date} {start_time}-{end_time}")
    ohlc_1min = fetch_1min_bars(symbol, date, start_time, end_time)

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

    # Set up the plot
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 16), height_ratios=[3, 1, 1])

    # Plot 1-minute close prices as line
    ax1.plot(price_line.index, price_line.values, color='blue', linewidth=1, alpha=0.7, label='1-min Close')

    # Plot trade markers
    if not sell_trades.empty:
        ax1.scatter(sell_trades['timestamp'], sell_trades['price'],
                   color='red', marker='v', s=30, alpha=0.7, label='SELL')

    if not buy_trades.empty:
        ax1.scatter(buy_trades['timestamp'], buy_trades['price'],
                   color='green', marker='^', s=30, alpha=0.7, label='BUY')

    # Plot window high/low for each trade (skip flatten trades with 0.0 ranges)
    for _, trade in df_trades.iterrows():
        if trade['window_high'] != 0.0 or trade['window_low'] != 0.0:  # Skip flatten trades
            timestamp = trade['timestamp']
            # Plot window high as orange line
            ax1.plot([timestamp, timestamp], [trade['window_low'], trade['window_high']],
                    color='orange', alpha=0.6, linewidth=2)
            # Mark window high and low points
            ax1.scatter([timestamp], [trade['window_high']],
                       color='orange', marker='_', s=40, alpha=0.8)
            ax1.scatter([timestamp], [trade['window_low']],
                       color='orange', marker='_', s=40, alpha=0.8)

    # Add window range to legend (just once)
    if not df_trades.empty:
        ax1.plot([], [], color='orange', alpha=0.6, linewidth=2, label='Window Range (High-Low)')

    # Simple legend (no candlestick patches needed)

    # Formatting
    ax1.set_title(f'{backtest_info["symbol"]} Fade Trading - {backtest_info["date"]} {backtest_info["start_time"]}-{backtest_info["end_time"]}')
    ax1.set_ylabel('Price ($)', fontsize=12)
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # Format x-axis
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    ax1.xaxis.set_major_locator(mdates.MinuteLocator(interval=1))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)

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
        ax2.plot(position_times, positions, color='blue', linewidth=2, label='Position')
        ax2.axhline(y=0, color='black', linestyle='--', alpha=0.5)
        ax2.set_ylabel('Position (Shares)', fontsize=12)
        ax2.grid(True, alpha=0.3)

        # Format x-axis
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        ax2.xaxis.set_major_locator(mdates.MinuteLocator(interval=1))
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)

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
        ax3.set_xlabel('Time', fontsize=12)
        ax3.grid(True, alpha=0.3)

        # Format x-axis
        ax3.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        ax3.xaxis.set_major_locator(mdates.MinuteLocator(interval=1))
        plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45)

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