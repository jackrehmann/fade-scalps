#!/usr/bin/env python3
"""
Fade Trading System - Pure Python Implementation
Executes inverse positions based on recent price movements.
"""

import json
import time
import threading
import logging
import os
from datetime import datetime, timedelta, time as dt_time
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order

# Ensure logs directory exists
os.makedirs('logs', exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('logs/fade_trader.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class PricePoint:
    """Single price observation"""
    timestamp: float
    price: float

@dataclass
class FadeSignal:
    """Trading signal from fade strategy"""
    symbol: str
    action: str  # "BUY" or "SELL"
    quantity: int
    reason: str
    price_move: float
    window_high: float = 0.0
    window_low: float = 0.0
    current_price: float = 0.0

class PriceHistory:
    """Rolling price history with fade signal calculation"""

    def __init__(self, window_minutes: float = 2.0):
        self.window_seconds = window_minutes * 60
        self.prices = deque()

    def add_price(self, price: float, timestamp: float = None):
        """Add new price point and clean old data"""
        if timestamp is None:
            timestamp = time.time()

        # Remove old prices outside window before adding new one
        cutoff = timestamp - self.window_seconds
        removed_count = 0
        while self.prices and self.prices[0].timestamp < cutoff:
            removed_price = self.prices.popleft()
            removed_count += 1

        # Debug logging for first few calls (disabled)
        # if len(self.prices) < 20:
        #     print(f"DEBUG: timestamp={timestamp}, cutoff={cutoff}, removed={removed_count}, window_size={len(self.prices)}")

        # Add new price
        self.prices.append(PricePoint(timestamp, price))

    def get_price_move(self) -> tuple[float, float, float, float]:
        """Calculate max move from current price to either high or low in window"""
        if len(self.prices) < 2:
            return 0.0, 0.0, 0.0, 0.0

        prices = [p.price for p in self.prices]
        current_price = prices[-1]
        max_price = max(prices)
        min_price = min(prices)

        # Calculate distance from current to high and low
        move_from_high = max_price - current_price    # How far down from high
        move_from_low = current_price - min_price     # How far up from low

        # Return the larger absolute move, with proper sign
        if move_from_high >= move_from_low:
            price_move = -move_from_high  # Negative = down from high (fade with BUY)
        else:
            price_move = move_from_low    # Positive = up from low (fade with SELL)

        return price_move, current_price, max_price, min_price

    def get_latest_price(self) -> Optional[float]:
        """Get most recent price"""
        return self.prices[-1].price if self.prices else None

class FadeEngine:
    """Core fade trading logic"""

    def __init__(self, config: dict):
        self.shares_per_dollar = config.get('shares_per_dollar', 100)
        self.min_move_threshold = config.get('min_move_threshold', 1.50)
        self.time_window_minutes = config.get('time_window_minutes', 2.0)
        self.max_position = config.get('max_position', 5000)

        # Track price history for each symbol
        self.price_histories: Dict[str, PriceHistory] = {}

        # Track current positions and peak positions for ratchet behavior
        self.positions: Dict[str, int] = {}
        self.peak_positions: Dict[str, int] = {}

        logger.info(f"FadeEngine initialized: {self.shares_per_dollar} shares/$1, "
                   f"${self.min_move_threshold} threshold, {self.time_window_minutes}min window")

    def update_price(self, symbol: str, price: float, timestamp: float = None) -> Optional[FadeSignal]:
        """Update price and check for fade signal"""

        # Check market hours - only trade between 9:30 AM and 4:00 PM ET
        if timestamp is None:
            # Live trading: use current system time
            current_time = datetime.now().time()
        else:
            # Backtesting: use provided timestamp
            current_time = datetime.fromtimestamp(timestamp).time()

        market_open = dt_time(9, 30)  # 9:30 AM ET
        market_close = dt_time(16, 0)  # 4:00 PM ET

        if not (market_open <= current_time <= market_close):
            # Return None to prevent trading outside market hours
            return None

        # Initialize price history if needed
        if symbol not in self.price_histories:
            self.price_histories[symbol] = PriceHistory(self.time_window_minutes)
            self.positions[symbol] = 0
            self.peak_positions[symbol] = 0

        # Add new price with timestamp
        self.price_histories[symbol].add_price(price, timestamp)

        # Calculate price move and get actual window values
        price_move, current_price, window_high, window_low = self.price_histories[symbol].get_price_move()

        abs_move = abs(price_move)
        current_position = self.positions[symbol]

        # Calculate unified move based on position
        if current_position == 0:
            move = price_move  # Use current window-based move
        elif current_position > 0:  # Long position
            move = current_price - window_high  # Negative when below high (unfavorable)
        else:  # Short position
            move = current_price - window_low   # Positive when above low (unfavorable)

        # Helper function for position decisions
        def can_contract_position():
            """Determine if we should contract (reduce) position"""
            if current_position == 0:
                return False  # Can't contract from flat
            # Contract when move is diminishing (less than threshold)
            return abs(move) < self.min_move_threshold

        # Main position logic - action-based decisions
        if abs(move) >= self.min_move_threshold:
            # EXPAND: Build up position using existing expansion logic
            excess_move = abs(move) - self.min_move_threshold
            goal_position_size = int(excess_move * self.shares_per_dollar)

            # Determine direction (fade = opposite to move)
            if price_move > 0:  # Up move, go short
                new_goal_position = -goal_position_size
            else:  # Down move, go long
                new_goal_position = goal_position_size

            # Only increase position size (ratchet up)
            if abs(new_goal_position) > abs(current_position):
                goal_position = new_goal_position
                self.peak_positions[symbol] = goal_position
            else:
                goal_position = current_position  # Hold current position

        elif can_contract_position():
            # CONTRACT: Reduce position using unified move-based scaling
            peak_position = self.peak_positions[symbol]

            # Scale position based on remaining favorable move
            percent_remaining = max(0, abs(move) / self.min_move_threshold) if self.min_move_threshold > 0 else 0
            goal_position = int(peak_position * percent_remaining)

            # ONLY contract - never expand beyond current position
            if abs(goal_position) > abs(current_position):
                goal_position = current_position

            # Zero out tiny positions
            if abs(goal_position) < 10:
                goal_position = 0

            # Reset peak when we reach zero
            if goal_position == 0:
                self.peak_positions[symbol] = 0

        else:
            # HOLD: No position change
            if current_position == 0:
                return None  # Stay flat
            goal_position = current_position  # Hold current position

        # Set excess_move for reason field
        if abs(move) >= self.min_move_threshold:
            excess_move = abs(move) - self.min_move_threshold
        else:
            excess_move = 0.0

        # Calculate trade needed
        trade_quantity = goal_position - current_position

        # Only trade if we need to change position significantly
        if abs(trade_quantity) < 10:  # Minimum 10 share trade size
            return None

        # Determine action and quantity
        if trade_quantity > 0:
            action = "BUY"
            quantity = trade_quantity
        else:
            action = "SELL"
            quantity = abs(trade_quantity)

        # Check position limits
        if abs(goal_position) > self.max_position:
            logger.warning(f"{symbol}: Goal position {goal_position} exceeds limit {self.max_position}, skipping trade")
            return None

        # Update position
        self.positions[symbol] = goal_position

        # Determine if this is expanding (fade) or reducing (unwind) position
        is_expanding = abs(goal_position) > abs(current_position)

        if is_expanding:
            reason = f"Fade ${price_move:.2f} move (excess: ${excess_move:.2f})"
        else:
            reason = f"Reduce ${price_move:.2f} move (excess: ${excess_move:.2f})"

        signal = FadeSignal(
            symbol=symbol,
            action=action,
            quantity=quantity,
            reason=reason,
            price_move=price_move,
            window_high=window_high,
            window_low=window_low,
            current_price=current_price
        )

        logger.info(f"FADE SIGNAL: {signal}")
        return signal

class IBKRClient(EWrapper, EClient):
    """IBKR connection and trading interface"""

    def __init__(self, fade_engine: FadeEngine, config: dict):
        EClient.__init__(self, self)
        self.fade_engine = fade_engine
        self.config = config
        self.next_order_id = None
        self.connected = False

        # Market data subscriptions
        self.subscriptions: Dict[str, int] = {}  # symbol -> reqId
        self.next_req_id = 1000

        # Keep last bid/ask per symbol for midpoint calculation
        self.last_bid: Dict[str, float] = {}
        self.last_ask: Dict[str, float] = {}

        # Trade storage for dry run mode
        self.dry_run_trades = []
        self.start_time = datetime.now()

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson="", *args):
        # Filter out noisy status messages but log all actual errors
        noisy_status = {2104, 2106, 2158, 1102}
        if errorCode not in noisy_status:
            logger.error(f"[reqId={reqId}] IB Error {errorCode}: {errorString}")

    def marketDataType(self, reqId, marketDataType):
        """Log market data type - 1=live, 2=frozen, 3=delayed, 4=delayed-frozen"""
        data_types = {1: "LIVE", 2: "FROZEN", 3: "DELAYED", 4: "DELAYED-FROZEN"}
        logger.info(f"Market data type for reqId={reqId}: {marketDataType} ({data_types.get(marketDataType, 'UNKNOWN')})")

    def nextValidId(self, orderId):
        logger.info(f"Connected to IBKR! Next order ID: {orderId}")
        self.next_order_id = orderId
        self.connected = True

    def tickPrice(self, reqId, tickType, price, attrib):
        """Handle real-time price updates"""
        symbol = self.get_symbol_from_req_id(reqId)
        if not symbol or price <= 0:
            return

        if tickType == 1:   # BID
            self.last_bid[symbol] = price
            ask = self.last_ask.get(symbol)
            if ask:  # Have both sides -> use midpoint
                mid = 0.5 * (price + ask)
                current_time = datetime.now().strftime("%H:%M:%S")
                logger.info(f"[{current_time}] {symbol} MID: ${mid:.2f} (bid: ${price:.2f}, ask: ${ask:.2f})")
                signal = self.fade_engine.update_price(symbol, mid)
                if signal:
                    self.execute_fade_signal(signal)

        elif tickType == 2: # ASK
            self.last_ask[symbol] = price
            bid = self.last_bid.get(symbol)
            if bid:  # Have both sides -> use midpoint
                mid = 0.5 * (bid + price)
                current_time = datetime.now().strftime("%H:%M:%S")
                logger.info(f"[{current_time}] {symbol} MID: ${mid:.2f} (bid: ${bid:.2f}, ask: ${price:.2f})")
                signal = self.fade_engine.update_price(symbol, mid)
                if signal:
                    self.execute_fade_signal(signal)

        elif tickType == 4: # LAST (fallback when available)
            current_time = datetime.now().strftime("%H:%M:%S")
            logger.info(f"[{current_time}] {symbol} LAST: ${price:.2f}")
            signal = self.fade_engine.update_price(symbol, price)
            if signal:
                self.execute_fade_signal(signal)

    def get_symbol_from_req_id(self, reqId: int) -> Optional[str]:
        """Find symbol associated with request ID"""
        for symbol, req_id in self.subscriptions.items():
            if req_id == reqId:
                return symbol
        return None

    def subscribe_to_symbol(self, symbol: str):
        """Subscribe to real-time data for symbol"""
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"

        # Add primary exchange for better contract specification
        primary_exchanges = {"TSLA": "NASDAQ", "AAPL": "NASDAQ", "NVDA": "NASDAQ"}
        contract.primaryExchange = primary_exchanges.get(symbol, "NASDAQ")

        req_id = self.next_req_id
        self.next_req_id += 1

        self.subscriptions[symbol] = req_id
        # Request real-time market data (will now get bid/ask ticks)
        self.reqMktData(req_id, contract, "", False, False, [])

        logger.info(f"Subscribed to {symbol} on {contract.primaryExchange} (reqId: {req_id})")

    def execute_fade_signal(self, signal: FadeSignal):
        """Execute fade trading signal"""
        if not self.connected or self.next_order_id is None:
            logger.error("Cannot execute trade: not connected to IBKR")
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

        # Check for dry run mode
        if hasattr(self, 'config') and self.config.get('dry_run', False):
            logger.info(f"DRY RUN: Would {signal.action} {signal.quantity} {signal.symbol} "
                       f"at market (Order ID: {order_id}) - NO ACTUAL ORDER PLACED")

            # Store dry run trade for later analysis
            trade_record = {
                'timestamp': datetime.now().isoformat(),
                'symbol': signal.symbol,
                'action': signal.action,
                'quantity': signal.quantity,
                'price': signal.current_price,
                'reason': signal.reason,
                'price_move': signal.price_move,
                'window_high': signal.window_high,
                'window_low': signal.window_low,
                'current_price': signal.current_price,
                'order_id': order_id
            }
            self.dry_run_trades.append(trade_record)
        else:
            self.placeOrder(order_id, contract, order)
            logger.info(f"TRADE EXECUTED: {signal.action} {signal.quantity} {signal.symbol} "
                       f"at market (Order ID: {order_id})")

    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice,
                   permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        """Handle order status updates"""
        logger.info(f"Order {orderId}: {status}, Filled: {filled}, Avg: ${avgFillPrice}")

    def save_dry_run_trades(self):
        """Save dry run trades to JSON file"""
        if not self.dry_run_trades:
            logger.info("No dry run trades to save")
            return

        import json

        # Create filename with timestamp
        end_time = datetime.now()
        symbols_str = "_".join(self.config.get('symbols', ['UNKNOWN']))
        start_str = self.start_time.strftime("%Y%m%d_%H%M")
        end_str = end_time.strftime("%H%M")
        filename = f"live_dryrun_{symbols_str}_{start_str}-{end_str}.json"

        # Create trade summary
        trade_data = {
            'session_info': {
                'symbols': self.config.get('symbols', []),
                'start_time': self.start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'duration_minutes': (end_time - self.start_time).total_seconds() / 60,
                'shares_per_dollar': self.config.get('shares_per_dollar', 0),
                'min_move_threshold': self.config.get('min_move_threshold', 0),
                'time_window_minutes': self.config.get('time_window_minutes', 0),
                'max_position': self.config.get('max_position', 0),
                'total_trades': len(self.dry_run_trades)
            },
            'trades': self.dry_run_trades
        }

        # Save to file
        try:
            with open(filename, 'w') as f:
                json.dump(trade_data, f, indent=2, default=str)
            logger.info(f"💾 Dry run trades saved to: {filename}")
            print(f"💾 Dry run trades saved to: {filename}")
        except Exception as e:
            logger.error(f"Failed to save dry run trades: {e}")

    def disconnect(self):
        """Override disconnect to save dry run trades"""
        if self.config.get('dry_run', False):
            self.save_dry_run_trades()
        super().disconnect()

class FadeTrader:
    """Main application orchestrating the fade trading system"""

    def __init__(self, config_path: str = "config.json"):
        self.config = self.load_config(config_path)
        self.fade_engine = FadeEngine(self.config)
        self.ibkr_client = IBKRClient(self.fade_engine, self.config)
        self.running = False

    def load_config(self, config_path: str) -> dict:
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            logger.info(f"Configuration loaded from {config_path}")
            return config
        except FileNotFoundError:
            logger.error(f"Config file {config_path} not found!")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {config_path}: {e}")
            raise

    def connect_to_ibkr(self):
        """Connect to IBKR Gateway"""
        host = self.config.get('ibkr_host', '127.0.0.1')
        port = self.config.get('ibkr_port', 4002)  # Gateway paper trading
        client_id = self.config.get('client_id', 1)

        logger.info(f"Connecting to IBKR at {host}:{port}")
        self.ibkr_client.connect(host, port, client_id)

        # Start API thread
        api_thread = threading.Thread(target=self.ibkr_client.run, daemon=True)
        api_thread.start()

        # Request order IDs and force live data mode
        self.ibkr_client.reqIds(-1)  # Ensure nextValidId fires
        self.ibkr_client.reqMarketDataType(1)  # 1 = live data

        # Wait for connection
        timeout = 10
        start_time = time.time()
        while not self.ibkr_client.connected and (time.time() - start_time) < timeout:
            time.sleep(0.1)

        if not self.ibkr_client.connected:
            raise ConnectionError("Failed to connect to IBKR")

        logger.info("Successfully connected to IBKR")

    def start_trading(self):
        """Start the fade trading system"""
        logger.info("Starting Fade Trading System")

        try:
            # Connect to IBKR
            self.connect_to_ibkr()

            # Subscribe to symbols
            symbols = self.config.get('symbols', ['AAPL', 'TSLA', 'NVDA'])
            for symbol in symbols:
                self.ibkr_client.subscribe_to_symbol(symbol)

            # Main trading loop
            self.running = True
            logger.info("Fade trading system is now active!")

            while self.running:
                time.sleep(1)  # Keep main thread alive

        except KeyboardInterrupt:
            logger.info("Shutdown requested by user")
        except Exception as e:
            logger.error(f"Fatal error: {e}")
        finally:
            self.stop_trading()

    def stop_trading(self):
        """Stop the trading system"""
        logger.info("Stopping Fade Trading System")
        self.running = False

        if self.ibkr_client.isConnected():
            self.ibkr_client.disconnect()

        # Print final positions
        logger.info("Final positions:")
        for symbol, position in self.fade_engine.positions.items():
            if position != 0:
                logger.info(f"  {symbol}: {position} shares")

def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Fade Trading System - Live Trading')
    parser.add_argument('--symbols', nargs='+', default=None,
                        help='Symbols to trade (e.g., TSLA AAPL)')
    parser.add_argument('--shares-per-dollar', type=float, default=None,
                        help='Number of shares to trade per $1 of excess move')
    parser.add_argument('--min-move-thresh', type=float, default=None,
                        help='Minimum price move required to trigger trades in $')
    parser.add_argument('--time-window', type=float, default=None,
                        help='Rolling window for calculating price range in minutes')
    parser.add_argument('--max-position', type=int, default=None,
                        help='Maximum position size limit in shares')
    parser.add_argument('--dry-run', action='store_true',
                        help='Enable dry run mode (no actual orders)')

    args = parser.parse_args()

    print("Fade Trading System - Pure Python Implementation")
    print("=" * 50)

    try:
        # Create trader with config overrides
        trader = FadeTrader()

        # Override config with command line arguments
        if args.symbols:
            trader.config['symbols'] = args.symbols
        if args.shares_per_dollar is not None:
            trader.config['shares_per_dollar'] = args.shares_per_dollar
        if args.min_move_thresh is not None:
            trader.config['min_move_threshold'] = args.min_move_thresh
        if args.time_window is not None:
            trader.config['time_window_minutes'] = args.time_window
        if args.max_position is not None:
            trader.config['max_position'] = args.max_position
        if args.dry_run:
            trader.config['dry_run'] = True

        # Update the fade engine with new config
        trader.fade_engine = FadeEngine(trader.config)
        trader.ibkr_client.fade_engine = trader.fade_engine

        # Show active configuration
        print(f"Trading symbols: {trader.config['symbols']}")
        print(f"Strategy params: shares_per_dollar={trader.config['shares_per_dollar']}, "
              f"min_move_thresh=${trader.config['min_move_threshold']}, "
              f"time_window={trader.config['time_window_minutes']}min, "
              f"max_position={trader.config['max_position']}")
        print(f"Dry run mode: {'ENABLED' if trader.config.get('dry_run', False) else 'DISABLED'}")
        print("=" * 50)

        trader.start_trading()
    except Exception as e:
        logger.error(f"Failed to start trading system: {e}")
        return 1

    return 0

if __name__ == "__main__":
    exit(main())