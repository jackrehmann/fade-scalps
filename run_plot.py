#!/usr/bin/env python3
"""
Convenience script to plot trades from root directory
"""
import sys
import os

# Add src directory to Python path
src_path = os.path.join(os.path.dirname(__file__), 'src')
sys.path.insert(0, src_path)

# Import plot_trades directly and run
from plot_trades import plot_backtest_trades

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python plot_trades.py <backtest_json_file>")
        sys.exit(1)

    json_file = sys.argv[1]
    print(f"Plotting: {json_file}")
    plot_backtest_trades(json_file)