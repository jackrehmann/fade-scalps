#!/usr/bin/env python3
"""
Live Trading for Fade Trading System
Uses IBKR real-time data with the same FadeEngine used for backtesting
"""

import time
import threading
from datetime import datetime
from typing import List, Dict, Optional
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
try:
    from .fade_trader import FadeEngine
except ImportError:
    from fade_trader import FadeEngine

class LiveTradingClient(EWrapper, EClient):
    """IBKR client for live fade trading"""

    def __init__(self, symbols: List[str], config: Dict, simulate_only: bool = True):
        EClient.__init__(self, self)
        self.symbols = symbols
        self.config = config
        self.simulate_only = simulate_only

        # Initialize fade engine (SAME ENGINE AS BACKTEST)
        self.fade_engine = FadeEngine(config)

        # Track subscriptions and orders
        self.subscriptions = {}  # req_id -> symbol
        self.next_req_id = 8000
        self.next_order_id = None
        self.connected = False

        # Live trading state
        self.trades_today = []
        self.live_positions = {}

        print(f"[LIVE] Initializing live trader for {symbols}")
        print(f"[LIVE] Config: {config}")
        print(f"[LIVE] Simulate Only: {simulate_only} (True=memory only, False=send to IBKR)")

    def error(self, reqId, errorCode, errorString, *args):
        # Handle both parameter orders - sometimes errorCode and errorString are swapped
        actual_error_code = errorString if isinstance(errorString, int) else errorCode
        if actual_error_code not in [2104, 2106, 2158, 1102]:  # Skip connection status
            print(f'[LIVE ERROR] {actual_error_code}: {errorCode if isinstance(errorString, int) else errorString}')

    def nextValidId(self, orderId):
        print(f'[LIVE] ✅ Connected to IBKR! Next order ID: {orderId}')
        self.next_order_id = orderId
        self.connected = True

        # Subscribe to real-time data for all symbols
        for symbol in self.symbols:
            self._subscribe_to_symbol(symbol)

        print(f'[LIVE] 🚀 Live trading active for {len(self.symbols)} symbols')

    def _subscribe_to_symbol(self, symbol: str):
        """Subscribe to real-time market data"""
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"

        req_id = self.next_req_id
        self.next_req_id += 1
        self.subscriptions[req_id] = symbol

        # Use default tick types (includes bid, ask, last price + some noise we'll filter)
        self.reqMktData(req_id, contract, "", False, False, [])
        print(f'[LIVE] 📊 Subscribed to {symbol} (req_id: {req_id})')

    def tickString(self, reqId, tickType, value):
        """Filter out noisy IBKR status messages"""
        # Block exchange info and other noise - we only care about prices
        noisy_tick_types = {32, 33, 45, 84}  # 32=bid exchange, 33=ask exchange, 45=timestamp, 84=status
        if tickType not in noisy_tick_types and reqId in self.subscriptions:
            symbol = self.subscriptions[reqId]
            print(f"[LIVE] {symbol} tickString: type={tickType}, value={value}")

    def tickSize(self, reqId, tickType, size):
        """Block all tickSize noise - we only care about prices"""
        pass

    def tickPrice(self, reqId, tickType, price, attrib):
        """Process real-time price ticks"""
        # Accept multiple tick types for price: 1=bid, 2=ask, 4=last, 6=high, 7=low, 9=close
        if tickType in [1, 2, 4] and reqId in self.subscriptions:  # Bid, Ask, or Last price
            symbol = self.subscriptions[reqId]
            timestamp = datetime.now()

            # Log price updates on EVERY price change
            current_position = self.live_positions.get(symbol, 0)
            print(f"[LIVE] {timestamp.strftime('%H:%M:%S')} {symbol} ${price:.2f} | Position: {current_position} shares")

            # Process through fade engine (SAME ENGINE AS BACKTEST)
            signal = self.fade_engine.update_price(symbol, price, timestamp.timestamp())

            if signal:
                print(f"   🎯 FADE SIGNAL: {signal.action} {signal.quantity} shares")
                print(f"   💡 Reason: {signal.reason}")

                if self.simulate_only:
                    self._simulate_trade(signal, price, timestamp)
                else:
                    self._send_to_ibkr(signal, price, timestamp)

    def _simulate_trade(self, signal, price: float, timestamp: datetime):
        """Execute simulated trade (memory only)"""
        trade = {
            'timestamp': timestamp,
            'symbol': signal.symbol,
            'action': signal.action,
            'quantity': signal.quantity,
            'price': price,
            'reason': signal.reason,
            'type': 'SIMULATED'
        }

        self.trades_today.append(trade)

        # Update paper position
        if signal.symbol not in self.live_positions:
            self.live_positions[signal.symbol] = 0

        if signal.action == 'BUY':
            self.live_positions[signal.symbol] += signal.quantity
        else:
            self.live_positions[signal.symbol] -= signal.quantity

        print(f"   📝 SIMULATED: {signal.action} {signal.quantity} {signal.symbol} @ ${price:.2f}")
        print(f"   📈 Position: {self.live_positions[signal.symbol]} shares")

    def _send_to_ibkr(self, signal, price: float, timestamp: datetime):
        """Send trade order to IBKR (paper or live account depending on connection)"""
        if not self.connected or self.next_order_id is None:
            print(f"   ❌ Cannot execute trade: not connected")
            return

        # Create contract
        contract = Contract()
        contract.symbol = signal.symbol
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"

        # Create market order
        order = Order()
        order.action = signal.action
        order.totalQuantity = signal.quantity
        order.orderType = "MKT"

        # Place order
        order_id = self.next_order_id
        self.next_order_id += 1

        self.placeOrder(order_id, contract, order)

        trade = {
            'timestamp': timestamp,
            'symbol': signal.symbol,
            'action': signal.action,
            'quantity': signal.quantity,
            'price': price,
            'reason': signal.reason,
            'type': 'IBKR_ORDER',
            'order_id': order_id
        }

        self.trades_today.append(trade)

        print(f"   💰 IBKR ORDER: {signal.action} {signal.quantity} {signal.symbol} (Order ID: {order_id})")

    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice,
                   permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        """Handle order status updates"""
        print(f"[LIVE] Order {orderId}: {status}, Filled: {filled} @ ${avgFillPrice:.2f}")

    def get_daily_summary(self) -> Dict:
        """Get summary of today's trading"""
        summary = {
            'total_trades': len(self.trades_today),
            'symbols_traded': list(set(t['symbol'] for t in self.trades_today)),
            'positions': self.live_positions.copy(),
            'trades': self.trades_today.copy()
        }

        # Calculate simple P&L for simulated trades
        if self.simulate_only:
            total_pnl = 0.0
            for symbol, position in self.live_positions.items():
                if position != 0:
                    # Find trades for this symbol to estimate P&L
                    symbol_trades = [t for t in self.trades_today if t['symbol'] == symbol]
                    if symbol_trades:
                        avg_price = sum(t['price'] for t in symbol_trades) / len(symbol_trades)
                        # This is a rough estimate - real P&L would need current market price
                        total_pnl += position * avg_price * 0.01  # Assume 1% move

            summary['estimated_pnl'] = total_pnl

        return summary

def _flatten_live_positions(client, simulate_only: bool):
    """Flatten all positions at end of live trading session"""
    # Get current market data to use as closing price
    # For now, use last trade price from memory
    for symbol, position in client.live_positions.items():
        if position != 0:
            # Find last price for this symbol from recent trades
            symbol_trades = [t for t in client.trades_today if t['symbol'] == symbol]
            if symbol_trades:
                last_price = symbol_trades[-1]['price']

                # Create flattening trade
                if position > 0:
                    action = "SELL"
                    quantity = position
                else:
                    action = "BUY"
                    quantity = abs(position)

                if simulate_only:
                    trade = {
                        'timestamp': datetime.now(),
                        'symbol': symbol,
                        'action': action,
                        'quantity': quantity,
                        'price': last_price,
                        'reason': 'End of session - flatten position',
                        'type': 'SIMULATED'
                    }
                    client.trades_today.append(trade)
                    client.live_positions[symbol] = 0
                    print(f"[LIVE] 📋 SIMULATED: {action} {quantity} {symbol} @ ${last_price:.2f} - Flatten")
                else:
                    # Would send real flatten order to IBKR here
                    print(f"[LIVE] 📋 Would send {action} {quantity} {symbol} to flatten position")

def _save_live_trades_to_json(summary: Dict, end_time: str = None):
    """Save live trading session to JSON file"""
    import json
    import os
    from datetime import datetime as dt

    # Ensure results directory exists
    os.makedirs('results/backtests', exist_ok=True)

    # Create filename based on session info
    now = dt.now()
    date_str = now.strftime("%Y%m%d")
    start_time = "live"
    if end_time:
        end_str = end_time.replace(":", "")
        filename = f"results/backtests/live_{summary['symbols_traded'][0]}_{date_str}_{start_time}-{end_str}.json"
    else:
        time_str = now.strftime("%H%M")
        filename = f"results/backtests/live_{summary['symbols_traded'][0]}_{date_str}_{time_str}.json"

    # Prepare data similar to backtest format
    trade_data = {
        'session_info': {
            'symbols': summary['symbols_traded'],
            'date': date_str,
            'session_type': 'live_trading',
            'end_time': end_time,
            'total_trades': summary['total_trades'],
            'final_positions': summary['positions']
        },
        'trades': []
    }

    # Convert trades to JSON-serializable format
    for trade in summary['trades']:
        trade_copy = trade.copy()
        if hasattr(trade['timestamp'], 'isoformat'):
            trade_copy['timestamp'] = trade['timestamp'].isoformat()
        trade_data['trades'].append(trade_copy)

    # Save to file
    try:
        with open(filename, 'w') as f:
            json.dump(trade_data, f, indent=2, default=str)
        print(f"[LIVE] 💾 Session saved to: {filename}")
    except Exception as e:
        print(f"[LIVE] ❌ Error saving session: {e}")

def run_live_fade(symbols: List[str], simulate_only: bool = True, end_time: str = None, **config):
    """
    Run live fade trading

    Args:
        symbols: List of symbols to trade (e.g., ["TSLA", "AAPL"])
        simulate_only: If True, simulate trades in memory. If False, send orders to IBKR.
        end_time: Optional end time in HH:MM format (e.g., "10:30"). Will auto-stop and flatten.
        **config: Strategy parameters
    """

    # Default configuration
    default_config = {
        'shares_per_dollar': 100,
        'min_move_threshold': 1.50,
        'time_window_minutes': 2.0,
        'max_position': 5000
    }
    default_config.update(config)

    # Validate end_time format if provided
    if end_time:
        try:
            datetime.strptime(end_time, '%H:%M')
        except ValueError:
            print(f"[LIVE] ❌ Invalid end time format: {end_time}. Use HH:MM format (e.g., 10:30)")
            return

    # Create live trading client
    client = LiveTradingClient(symbols, default_config, simulate_only)

    try:
        # Connect to IBKR Gateway
        # Note: Port doesn't matter for simulate_only mode (only gets market data)
        # For IBKR orders: 4002=paper trading gateway, 4000=live trading gateway
        port = 4002  # Default to paper trading gateway port
        import random
        client_id = random.randint(1000, 9999)  # Random client ID to avoid conflicts
        client.connect('127.0.0.1', port, client_id)

        # Start API thread
        thread = threading.Thread(target=client.run, daemon=True)
        thread.start()

        # Wait for connection
        start_time = time.time()
        while not client.connected and (time.time() - start_time) < 10:
            time.sleep(0.1)

        if not client.connected:
            print("[LIVE] ❌ Failed to connect to IBKR")
            return

        print(f"\n[LIVE] Trading session started at {datetime.now().strftime('%H:%M:%S')}")
        if end_time:
            print(f"[LIVE] Will auto-stop at {end_time} and flatten positions")
        print("[LIVE] Press Ctrl+C to stop and view summary")

        # Main trading loop
        while True:
            # Check if we've reached end time
            if end_time:
                try:
                    current_time = datetime.now().strftime('%H:%M')
                    if current_time >= end_time:
                        print(f"\n[LIVE] 🕒 Reached end time {end_time} - auto-stopping...")
                        break
                except Exception as e:
                    print(f"[LIVE] ⚠️  Error checking end time: {e}")
            time.sleep(1)

        # If we reach here, we hit end_time (not Ctrl+C)
        print(f"\n[LIVE] 📋 Flattening positions at end time...")
        _flatten_live_positions(client, simulate_only)

    except KeyboardInterrupt:
        print(f"\n[LIVE] 🛑 Stopping trading session...")

    finally:
        # Show daily summary (regardless of how we stopped)
        summary = client.get_daily_summary()
        print(f"\n📊 DAILY TRADING SUMMARY")
        print(f"   Total trades: {summary['total_trades']}")
        print(f"   Symbols traded: {summary['symbols_traded']}")

        if summary['positions']:
            print(f"   Final positions:")
            for symbol, position in summary['positions'].items():
                if position != 0:
                    print(f"     {symbol}: {position} shares")

        if simulate_only and 'estimated_pnl' in summary:
            print(f"   Estimated P&L: ${summary['estimated_pnl']:.2f}")

        # Show recent trades
        if summary['trades']:
            print(f"\n   Recent trades:")
            for trade in summary['trades'][-5:]:  # Last 5 trades
                print(f"     {trade['timestamp'].strftime('%H:%M:%S')} "
                      f"{trade['action']} {trade['quantity']} {trade['symbol']} @ ${trade['price']:.2f}")

        # Save trades to JSON file if there were any
        if summary['trades']:
            _save_live_trades_to_json(summary, end_time)

        if client.isConnected():
            client.disconnect()

def quick_live_test():
    """Quick test with simulation only"""
    print("Quick Live Trading Test (Simulation)")
    print("=" * 40)

    run_live_fade(
        symbols=["TSLA"],
        simulate_only=True,  # Memory simulation only
        shares_per_dollar=50,
        min_move_threshold=0.25  # Sensitive for testing
    )

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description='Live Fade Trading',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 live_trader.py TSLA --simulate-only
  python3 live_trader.py TSLA --send-to-ibkr --min-move-thresh 1.0
  python3 live_trader.py TSLA AAPL --shares-per-dollar 50
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

    # Strategy parameters
    parser.add_argument('--shares-per-dollar', type=float, default=100,
                       help='Number of shares to trade per $1 of excess move (default: 100)')
    parser.add_argument('--min-move-thresh', type=float, default=1.50,
                       help='Minimum price move required to trigger trades in $ (default: 1.50)')
    parser.add_argument('--time-window', type=float, default=2.0,
                       help='Rolling window for calculating price range in minutes (default: 2.0)')
    parser.add_argument('--max-position', type=int, default=5000,
                       help='Maximum position size limit in shares (default: 5000)')

    args = parser.parse_args()

    # Determine simulation mode
    simulate_only = not args.send_to_ibkr

    print(f"Live trading: {args.symbols}")
    print(f"Mode: {'Simulation only' if simulate_only else 'Send orders to IBKR'}")
    print(f"Strategy params: shares_per_dollar={args.shares_per_dollar}, min_move_thresh=${args.min_move_thresh}, time_window={args.time_window}min, max_position={args.max_position}")

    run_live_fade(
        symbols=args.symbols,
        simulate_only=simulate_only,
        shares_per_dollar=args.shares_per_dollar,
        min_move_threshold=args.min_move_thresh,
        time_window_minutes=args.time_window,
        max_position=args.max_position
    )