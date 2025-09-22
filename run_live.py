#!/usr/bin/env python3
"""
Convenience script to run live trading from root directory
"""
import sys
import os

# Add src directory to Python path
src_path = os.path.join(os.path.dirname(__file__), 'src')
sys.path.insert(0, src_path)

from live_trader import *

if __name__ == "__main__":
    # Import the main function from live_trader and run it
    import argparse

    parser = argparse.ArgumentParser(
        description='Live Fade Trading',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 run_live.py TSLA --simulate-only
  python3 run_live.py TSLA --send-to-ibkr --min-move-thresh 1.0
  python3 run_live.py TSLA AAPL --shares-per-dollar 50
        """
    )

    # Required arguments
    parser.add_argument('symbols', nargs='+', help='Stock symbols to trade (e.g., TSLA AAPL)')

    # Trading mode
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--simulate-only', action='store_true', default=True,
                      help='Simulate trades in memory only (default)')
    group.add_argument('--send-to-ibkr', action='store_true',
                      help='Send orders to IBKR (paper or live account)')
    group.add_argument('--offline-sim', action='store_true',
                      help='Offline simulation (no IBKR connection needed)')

    # Strategy parameters
    parser.add_argument('--shares-per-dollar', type=float, default=100,
                       help='Number of shares to trade per $1 of excess move (default: 100)')
    parser.add_argument('--min-move-thresh', type=float, default=1.50,
                       help='Minimum price move required to trigger trades in $ (default: 1.50)')
    parser.add_argument('--time-window', type=float, default=2.0,
                       help='Rolling window for calculating price range in minutes (default: 2.0)')
    parser.add_argument('--max-position', type=int, default=5000,
                       help='Maximum position size limit in shares (default: 5000)')
    parser.add_argument('--end-time', type=str,
                       help='Auto-stop time in HH:MM format (e.g., 10:30). Will flatten positions.')

    args = parser.parse_args()

    # Determine simulation mode
    if args.offline_sim:
        print("🔌 Offline simulation mode - testing strategy logic only")
        print("This is a placeholder for offline simulation")
        sys.exit(0)

    simulate_only = not args.send_to_ibkr

    print(f"Live trading: {args.symbols}")
    print(f"Mode: {'Simulation only' if simulate_only else 'Send orders to IBKR'}")
    print(f"Strategy params: shares_per_dollar={args.shares_per_dollar}, min_move_thresh=${args.min_move_thresh}, time_window={args.time_window}min, max_position={args.max_position}")

    run_live_fade(
        symbols=args.symbols,
        simulate_only=simulate_only,
        end_time=args.end_time,
        shares_per_dollar=args.shares_per_dollar,
        min_move_threshold=args.min_move_thresh,
        time_window_minutes=args.time_window,
        max_position=args.max_position
    )