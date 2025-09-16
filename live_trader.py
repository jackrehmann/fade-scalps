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
from fade_trader import FadeEngine

class LiveTradingClient(EWrapper, EClient):
    """IBKR client for live fade trading"""

    def __init__(self, symbols: List[str], config: Dict, paper_trading: bool = True):
        EClient.__init__(self, self)
        self.symbols = symbols
        self.config = config
        self.paper_trading = paper_trading

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
        print(f"[LIVE] Paper Trading: {paper_trading}")

    def error(self, reqId, errorCode, errorString, *args):
        if errorCode not in [2104, 2106, 2158]:  # Skip connection status
            print(f'[LIVE ERROR] {errorCode}: {errorString}')

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

        self.reqMktData(req_id, contract, "", False, False, [])
        print(f'[LIVE] 📊 Subscribed to {symbol} (req_id: {req_id})')

    def tickPrice(self, reqId, tickType, price, attrib):
        """Process real-time price ticks"""
        if tickType == 4 and reqId in self.subscriptions:  # Last price
            symbol = self.subscriptions[reqId]
            timestamp = datetime.now()

            # Process through fade engine (SAME ENGINE AS BACKTEST)
            signal = self.fade_engine.update_price(symbol, price)

            if signal:
                print(f"\n📊 {timestamp.strftime('%H:%M:%S')} {symbol} ${price:.2f}")
                print(f"   🎯 FADE SIGNAL: {signal.action} {signal.quantity} shares")
                print(f"   💡 Reason: {signal.reason}")

                if self.paper_trading:
                    self._execute_paper_trade(signal, price, timestamp)
                else:
                    self._execute_live_trade(signal, price, timestamp)

    def _execute_paper_trade(self, signal, price: float, timestamp: datetime):
        """Execute simulated trade (paper trading)"""
        trade = {
            'timestamp': timestamp,
            'symbol': signal.symbol,
            'action': signal.action,
            'quantity': signal.quantity,
            'price': price,
            'reason': signal.reason,
            'type': 'PAPER'
        }

        self.trades_today.append(trade)

        # Update paper position
        if signal.symbol not in self.live_positions:
            self.live_positions[signal.symbol] = 0

        if signal.action == 'BUY':
            self.live_positions[signal.symbol] += signal.quantity
        else:
            self.live_positions[signal.symbol] -= signal.quantity

        print(f"   📝 PAPER TRADE: {signal.action} {signal.quantity} {signal.symbol} @ ${price:.2f}")
        print(f"   📈 Position: {self.live_positions[signal.symbol]} shares")

    def _execute_live_trade(self, signal, price: float, timestamp: datetime):
        """Execute real trade (live trading)"""
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
            'type': 'LIVE',
            'order_id': order_id
        }

        self.trades_today.append(trade)

        print(f"   💰 LIVE TRADE: {signal.action} {signal.quantity} {signal.symbol} (Order ID: {order_id})")

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

        # Calculate simple P&L for paper trades
        if self.paper_trading:
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

def run_live_fade(symbols: List[str], paper_trading: bool = True, **config):
    """
    Run live fade trading

    Args:
        symbols: List of symbols to trade (e.g., ["TSLA", "AAPL"])
        paper_trading: If True, simulate trades. If False, execute real trades.
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

    # Create live trading client
    client = LiveTradingClient(symbols, default_config, paper_trading)

    try:
        # Connect to IBKR
        port = 4001 if paper_trading else 4000  # 4001=paper, 4000=live
        client.connect('127.0.0.1', port, 9999)

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
        print("[LIVE] Press Ctrl+C to stop and view summary")

        # Main trading loop
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print(f"\n[LIVE] 🛑 Stopping trading session...")

        # Show daily summary
        summary = client.get_daily_summary()
        print(f"\n📊 DAILY TRADING SUMMARY")
        print(f"   Total trades: {summary['total_trades']}")
        print(f"   Symbols traded: {summary['symbols_traded']}")

        if summary['positions']:
            print(f"   Final positions:")
            for symbol, position in summary['positions'].items():
                if position != 0:
                    print(f"     {symbol}: {position} shares")

        if paper_trading and 'estimated_pnl' in summary:
            print(f"   Estimated P&L: ${summary['estimated_pnl']:.2f}")

        # Show recent trades
        if summary['trades']:
            print(f"\n   Recent trades:")
            for trade in summary['trades'][-5:]:  # Last 5 trades
                print(f"     {trade['timestamp'].strftime('%H:%M:%S')} "
                      f"{trade['action']} {trade['quantity']} {trade['symbol']} @ ${trade['price']:.2f}")

    finally:
        if client.isConnected():
            client.disconnect()

def quick_live_test():
    """Quick test with paper trading"""
    print("Quick Live Trading Test (Paper)")
    print("=" * 35)

    run_live_fade(
        symbols=["TSLA"],
        paper_trading=True,
        shares_per_dollar=50,
        min_move_threshold=0.25  # Sensitive for testing
    )

if __name__ == "__main__":
    quick_live_test()