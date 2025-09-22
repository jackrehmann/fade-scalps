#!/usr/bin/env python3
"""
Convert fade trading JSON files to CSV for analysis
"""

import json
import pandas as pd
import sys
import re
from datetime import datetime

def extract_excess_move(reason):
    """Extract excess move amount from reason string"""
    match = re.search(r'excess: \$([0-9.-]+)', reason)
    return float(match.group(1)) if match else 0.0

def extract_price_move(reason):
    """Extract price move amount from reason string"""
    if 'Fade' in reason or 'Reduce' in reason:
        match = re.search(r'(Fade|Reduce) \$([0-9.-]+)', reason)
        return float(match.group(2)) if match else 0.0
    return 0.0

def get_trade_type(reason):
    """Determine if trade is fade, reduce, or flatten"""
    if 'Fade' in reason:
        return 'Fade'
    elif 'Reduce' in reason:
        return 'Reduce'
    elif 'flatten' in reason:
        return 'Flatten'
    else:
        return 'Other'

def json_to_csv(json_file, csv_file=None):
    """Convert JSON trading data to CSV"""

    # Load JSON data
    with open(json_file, 'r') as f:
        data = json.load(f)

    # Extract session info
    if 'backtest_info' in data:
        session_info = data['backtest_info']
        session_type = 'backtest'
    elif 'session_info' in data:
        session_info = data['session_info']
        session_type = session_info.get('session_type', 'live_trading')
    else:
        raise ValueError("Invalid file format")

    print(f"Session Type: {session_type}")
    print(f"Symbol: {session_info.get('symbol', session_info.get('symbols', ['UNKNOWN'])[0])}")
    print(f"Date: {session_info.get('date', 'UNKNOWN')}")
    print(f"Trades: {len(data['trades'])}")

    # Convert trades to DataFrame
    df = pd.DataFrame(data['trades'])

    if df.empty:
        print("No trades found!")
        return

    # Process timestamps
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['date'] = df['timestamp'].dt.date
    df['time'] = df['timestamp'].dt.strftime('%H:%M:%S.%f').str[:-3]  # Include milliseconds
    df['hour'] = df['timestamp'].dt.hour
    df['minute'] = df['timestamp'].dt.minute
    df['second'] = df['timestamp'].dt.second

    # Extract additional fields from reason
    df['excess_move'] = df['reason'].apply(extract_excess_move)
    df['price_move'] = df['reason'].apply(extract_price_move)
    df['trade_type'] = df['reason'].apply(get_trade_type)

    # Calculate running position
    df['position_after'] = 0
    position = 0
    for i, row in df.iterrows():
        if row['action'] == 'BUY':
            position += row['quantity']
        else:  # SELL
            position -= row['quantity']
        df.loc[i, 'position_after'] = position

    # Add position change
    df['position_change'] = df['quantity'] * df['action'].map({'BUY': 1, 'SELL': -1})

    # Calculate trade value
    df['trade_value'] = df['quantity'] * df['price']

    # Add session info columns
    df['session_type'] = session_type
    df['session_symbol'] = session_info.get('symbol', session_info.get('symbols', ['UNKNOWN'])[0])
    df['session_date'] = session_info.get('date', 'UNKNOWN')

    # Reorder columns for better readability
    columns_order = [
        'timestamp', 'date', 'time', 'hour', 'minute', 'second',
        'session_type', 'session_symbol', 'session_date',
        'symbol', 'action', 'quantity', 'price', 'trade_value',
        'position_change', 'position_after',
        'trade_type', 'reason', 'price_move', 'excess_move',
        'type'  # SIMULATED vs REAL
    ]

    # Only include columns that exist
    columns_order = [col for col in columns_order if col in df.columns]
    df = df[columns_order]

    # Generate CSV filename if not provided
    if csv_file is None:
        csv_file = json_file.replace('.json', '_trades.csv')

    # Save to CSV
    df.to_csv(csv_file, index=False)
    print(f"\n✅ Saved {len(df)} trades to: {csv_file}")

    # Print summary
    print(f"\n📊 SUMMARY:")
    print(f"   BUY trades: {len(df[df['action'] == 'BUY'])}")
    print(f"   SELL trades: {len(df[df['action'] == 'SELL'])}")
    print(f"   Fade trades: {len(df[df['trade_type'] == 'Fade'])}")
    print(f"   Reduce trades: {len(df[df['trade_type'] == 'Reduce'])}")
    print(f"   Flatten trades: {len(df[df['trade_type'] == 'Flatten'])}")
    print(f"   Price range: ${df['price'].min():.2f} - ${df['price'].max():.2f}")
    print(f"   Final position: {df['position_after'].iloc[-1]} shares")
    print(f"   Total shares traded: {df['quantity'].sum()}")

    return df

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python json_to_csv.py <json_file> [csv_file]")
        print("Example: python json_to_csv.py results/backtests/live_TSLA_20250918_live-1600.json")
        sys.exit(1)

    json_file = sys.argv[1]
    csv_file = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        json_to_csv(json_file, csv_file)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)