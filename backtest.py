#!/usr/bin/env python3
"""
Backtesting for Fade Trading System
Uses IBKR historical data with the same FadeEngine used for live trading

USAGE:
python3 backtest.py SYMBOL DATE START_TIME END_TIME [options]

EXAMPLES:
python3 backtest.py TSLA 20250915 09:30 09:50
python3 backtest.py TSLA 20250915 09:30 09:50 --min-move-thresh 3.0 --shares-per-dollar 150
python3 backtest.py TSLA 20250915 09:30 09:50 --time-window 1.5 --max-position 3000

STRATEGY PARAMETERS (can now be set via command line arguments):
--shares-per-dollar: Number of shares to trade per $1 of excess move (default: 100)
--min-move-thresh: Minimum price move required to trigger trades in $ (default: 2.50)
--time-window: Rolling window for calculating price range in minutes (default: 2.0)
--max-position: Maximum position size limit in shares (default: 5000)
--max-requests: Maximum number of IBKR data requests (default: 100)
"""

import time
import threading
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from fade_trader import FadeEngine

@dataclass
class BacktestResult:
    """Results from a backtest run"""
    symbol: str
    start_time: str
    end_time: str
    config: Dict
    total_trades: int
    total_pnl: float
    win_rate: float
    max_position: int
    final_position: int
    trades: List[Dict]
    price_data: List[Dict]

class BacktestClient(EWrapper, EClient):
    """IBKR client for historical backtesting"""

    def __init__(self, symbol: str, start_datetime: str, end_datetime: str, config: Dict):
        EClient.__init__(self, self)
        self.symbol = symbol
        self.start_datetime = start_datetime
        self.end_datetime = end_datetime
        self.config = config

        # Initialize fade engine with same logic as live trading
        self.fade_engine = FadeEngine(config)

        # Track results
        self.trades = []
        self.price_data = []
        self.finished = False

        # Multi-request handling for getting all ticks
        self.current_req_id = 6001
        self.total_ticks_received = 0
        self.requests_made = 0
        self.max_requests = 100  # Allow longer periods (IBKR allows ~60 per 10min)

        # Track pagination state
        self.last_tick_timestamp = None
        self.current_start_time = start_datetime  # Will be updated for each request
        self.target_end_time = end_datetime       # Fixed target end time

        print(f"[BACKTEST] Testing {symbol} from {start_datetime} to {end_datetime}")
        print(f"[BACKTEST] Config: {config}")
        print(f"[BACKTEST] Will make multiple 1000-tick requests to get complete data")

    def error(self, reqId, errorCode, errorString, *args):
        # Handle both parameter orders - sometimes errorCode and errorString are swapped
        actual_error_code = errorString if isinstance(errorString, int) else errorCode
        if actual_error_code not in [2104, 2106, 2158, 1102]:  # Skip connection status
            print(f'[BACKTEST ERROR] reqId={reqId}, errorCode={actual_error_code}: {errorCode if isinstance(errorString, int) else errorString}')
            # If this is related to our historical data request, mark as finished
            if reqId >= 6001:
                print(f'[BACKTEST] Error on historical data request - finishing')
                self.finished = True

    def nextValidId(self, orderId):
        print(f'[BACKTEST] Connected to IBKR, starting multi-request data collection...')
        print(f'[DEBUG] nextValidId callback working - orderId: {orderId}')
        self._request_next_batch()

    def _request_next_batch(self):
        """Request next batch of 1000 ticks using proper pagination"""
        if self.requests_made >= self.max_requests:
            print(f'[BACKTEST] ⚠️  Reached max requests limit ({self.max_requests})')
            self.finished = True
            threading.Timer(1.0, self.disconnect).start()
            return

        # Check if we've reached target end time
        if self.last_tick_timestamp:
            from datetime import datetime
            last_tick_dt = datetime.fromtimestamp(self.last_tick_timestamp)
            target_dt = datetime.strptime(self.target_end_time, "%Y%m%d %H:%M:%S US/Eastern")
            if last_tick_dt >= target_dt:
                print(f'[BACKTEST] ✅ Reached target end time: {target_dt.strftime("%H:%M:%S")}')
                self.finished = True
                threading.Timer(1.0, self.disconnect).start()
                return

        contract = Contract()
        contract.symbol = self.symbol
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"

        req_id = self.current_req_id
        self.current_req_id += 1
        self.requests_made += 1

        print(f'[BACKTEST] Request {self.requests_made}: Getting ticks from {self.current_start_time}')
        print(f'[BACKTEST] Target end time: {self.target_end_time}')

        self.reqHistoricalTicks(
            reqId=req_id,
            contract=contract,
            startDateTime=self.current_start_time,  # Use current pagination point
            endDateTime=self.target_end_time,       # Keep same end target
            numberOfTicks=1000,
            whatToShow="BID_ASK",
            useRth=1,
            ignoreSize=True,
            miscOptions=[]
        )

    def historicalTicksBidAsk(self, reqId, ticks, done):
        """Process historical ticks through fade engine"""
        print(f"[BACKTEST] Received historicalTicksBidAsk callback: {len(ticks)} ticks, done={done}")
        batch_size = len(ticks)
        self.total_ticks_received += batch_size

        # Show timestamp range for this batch
        if ticks:
            first_tick_time = datetime.fromtimestamp(ticks[0].time)
            last_tick_time = datetime.fromtimestamp(ticks[-1].time)
            print(f'[BACKTEST] Batch {self.requests_made}: {batch_size} ticks (total: {self.total_ticks_received})')
            print(f'[BACKTEST] Time range: {first_tick_time.strftime("%H:%M:%S")} to {last_tick_time.strftime("%H:%M:%S")}')
        else:
            print(f'[BACKTEST] Batch {self.requests_made}: {batch_size} ticks (total: {self.total_ticks_received})')

        for tick in ticks:
            # Use midpoint price (same as live trading would see)
            price = (tick.priceBid + tick.priceAsk) / 2.0
            timestamp = datetime.fromtimestamp(tick.time)

            # Store price data
            self.price_data.append({
                'timestamp': timestamp,
                'price': price,
                'bid': tick.priceBid,
                'ask': tick.priceAsk
            })

            # Process through fade engine (SAME ENGINE AS LIVE)
            signal = self.fade_engine.update_price(self.symbol, price, timestamp.timestamp())

            if signal:
                # Record simulated trade
                trade = {
                    'timestamp': timestamp,
                    'symbol': signal.symbol,
                    'action': signal.action,
                    'quantity': signal.quantity,
                    'price': price,
                    'reason': signal.reason,
                    'price_move': signal.price_move,
                    'window_high': signal.window_high,
                    'window_low': signal.window_low,
                    'current_price': signal.current_price
                }
                self.trades.append(trade)

                # Only print first few trades to avoid spam
                if len(self.trades) <= 5:
                    print(f"  📊 {timestamp.strftime('%H:%M:%S')} ${price:.2f}")
                    print(f"     🎯 {signal.action} {signal.quantity} shares - {signal.reason}")

        if done:
            # Update pagination state using last tick timestamp
            if ticks and len(ticks) > 0:
                last_tick = ticks[-1]
                self.last_tick_timestamp = last_tick.time

                # Convert to datetime for comparison
                last_dt = datetime.fromtimestamp(self.last_tick_timestamp)
                target_dt = datetime.strptime(self.target_end_time, "%Y%m%d %H:%M:%S US/Eastern").replace(tzinfo=None)

                # Update current_start_time for next request (1 second after last tick)
                next_start_dt = last_dt + timedelta(seconds=1)
                self.current_start_time = next_start_dt.strftime("%Y%m%d %H:%M:%S US/Eastern")

                if last_dt >= target_dt:
                    print(f'[BACKTEST] ✅ Reached target end time: {last_dt.strftime("%Y-%m-%d %H:%M:%S")}')
                    self._complete_backtest()
                    return

            # Continue pagination if we haven't reached end time yet
            if batch_size >= 1000:
                print(f'[BACKTEST] Requesting next batch...')
                threading.Timer(1.0, self._request_next_batch).start()
            else:
                print(f'[BACKTEST] ✅ Final batch received ({batch_size} ticks)')
                self._complete_backtest()

    def _complete_backtest(self):
        """Complete the backtest by flattening positions and saving results"""
        # Flatten all positions at end of simulation
        self._flatten_positions()
        # Save trades to JSON file as final step
        self._save_trades_to_json()
        self.finished = True
        threading.Timer(1.0, self.disconnect).start()

    def historicalTicksLast(self, reqId, ticks, done):
        """Fallback callback - shouldn't be called but let's check"""
        print(f"[DEBUG] Unexpected historicalTicksLast callback: {len(ticks)} ticks")

    def historicalTicks(self, reqId, ticks, done):
        """Another fallback callback"""
        print(f"[DEBUG] Unexpected historicalTicks callback: {len(ticks)} ticks")

        # Show timestamp range for this batch
        if ticks:
            first_tick_time = datetime.fromtimestamp(ticks[0].time)
            last_tick_time = datetime.fromtimestamp(ticks[-1].time)
            print(f'[BACKTEST] Batch {self.requests_made}: {batch_size} ticks (total: {self.total_ticks_received})')
            print(f'[BACKTEST] Time range: {first_tick_time.strftime("%H:%M:%S")} to {last_tick_time.strftime("%H:%M:%S")}')
        else:
            print(f'[BACKTEST] Batch {self.requests_made}: {batch_size} ticks (total: {self.total_ticks_received})')

        for tick in ticks:
            # Use midpoint price (same as live trading would see)
            price = (tick.priceBid + tick.priceAsk) / 2.0
            timestamp = datetime.fromtimestamp(tick.time)

            # Store price data
            self.price_data.append({
                'timestamp': timestamp,
                'price': price,
                'bid': tick.priceBid,
                'ask': tick.priceAsk
            })

            # Process through fade engine (SAME ENGINE AS LIVE)
            signal = self.fade_engine.update_price(self.symbol, price, timestamp.timestamp())

            if signal:
                # Record simulated trade
                trade = {
                    'timestamp': timestamp,
                    'symbol': signal.symbol,
                    'action': signal.action,
                    'quantity': signal.quantity,
                    'price': price,
                    'reason': signal.reason,
                    'price_move': signal.price_move,
                    'window_high': signal.window_high,
                    'window_low': signal.window_low,
                    'current_price': signal.current_price
                }
                self.trades.append(trade)

                # Only print first few trades to avoid spam
                if len(self.trades) <= 5:
                    print(f"  📊 {timestamp.strftime('%H:%M:%S')} ${price:.2f}")
                    print(f"     🎯 {signal.action} {signal.quantity} shares - {signal.reason}")

        if done:
            # Update pagination state using last tick timestamp
            if ticks and len(ticks) > 0:
                last_tick = ticks[-1]
                self.last_tick_timestamp = last_tick.time

                # Convert to datetime for next request start time
                last_tick_dt = datetime.fromtimestamp(self.last_tick_timestamp)

                # Start next request 1 second after last tick (IBKR best practice)
                next_start_dt = last_tick_dt + timedelta(seconds=1)
                self.current_start_time = next_start_dt.strftime("%Y%m%d %H:%M:%S US/Eastern")

                print(f'[BACKTEST] Last tick: {last_tick_dt.strftime("%H:%M:%S")}, next start: {next_start_dt.strftime("%H:%M:%S")}')

            # Continue requesting if we got substantial data and haven't reached target end
            if batch_size >= 100:  # Continue if we got meaningful data
                print(f'[BACKTEST] Got {batch_size} ticks, requesting more data...')
                # Adaptive delay: faster for fewer requests, slower to avoid rate limits
                delay = 0.5 if self.requests_made < 30 else 1.2
                threading.Timer(delay, self._request_next_batch).start()
            else:
                # Got very few ticks, likely at end of data
                print(f'[BACKTEST] ✅ Got final batch ({batch_size} ticks), processing complete')
                print(f'[BACKTEST] Total ticks collected: {self.total_ticks_received}')

                # Flatten all positions at end of simulation
                self._flatten_positions()

                # Save trades to JSON file as final step
                self._save_trades_to_json()

                self.finished = True
                threading.Timer(1.0, self.disconnect).start()

    def _flatten_positions(self):
        """Flatten all positions at end of simulation using last price"""
        if not self.price_data:
            return

        last_price = self.price_data[-1]['price']
        current_position = self.fade_engine.positions.get(self.symbol, 0)

        if current_position != 0:
            if current_position > 0:
                # Close long position
                action = "SELL"
                quantity = current_position
            else:
                # Close short position
                action = "BUY"
                quantity = abs(current_position)

            # Add flattening trade
            trade = {
                'timestamp': self.price_data[-1]['timestamp'],  # Keep as datetime object
                'symbol': self.symbol,
                'action': action,
                'quantity': quantity,
                'price': last_price,
                'reason': 'End of simulation - flatten position',
                'price_move': 0.0,  # Not a signal-driven trade
                'window_high': 0.0,
                'window_low': 0.0,
                'current_price': last_price
            }

            self.trades.append(trade)
            self.fade_engine.positions[self.symbol] = 0  # Set position to flat

            print(f'[BACKTEST] 📋 {action} {quantity} shares at ${last_price:.2f} - Flatten position')

    def _save_trades_to_json(self):
        """Save trades to JSON file when backtest completes"""
        if not self.trades:
            print("[BACKTEST] No trades to save")
            return

        import json
        from datetime import datetime as dt

        # Extract date/time from datetime strings
        start_parts = self.start_datetime.split()
        end_parts = self.end_datetime.split()
        date = start_parts[0]
        start_time = start_parts[1].split(':')[0] + start_parts[1].split(':')[1]  # HHMM format
        end_time = end_parts[1].split(':')[0] + end_parts[1].split(':')[1]      # HHMM format

        filename = f"backtest_{self.symbol}_{date}_{start_time}-{end_time}.json"

        # Get final results
        result = self.get_results()

        # Prepare data for JSON serialization
        trade_data = {
            'backtest_info': {
                'symbol': self.symbol,
                'date': date,
                'start_time': f"{start_time[:2]}:{start_time[2:]}",  # Convert back to HH:MM
                'end_time': f"{end_time[:2]}:{end_time[2:]}",        # Convert back to HH:MM
                'config': self.config,
                'total_trades': result.total_trades,
                'total_pnl': result.total_pnl,
                'win_rate': result.win_rate,
                'max_position': result.max_position,
                'final_position': result.final_position,
                'price_ticks': len(result.price_data)
            },
            'trades': []
        }

        # Convert trades to JSON-serializable format
        for i, trade in enumerate(result.trades):
            try:
                trade_copy = trade.copy()
                # Handle both datetime objects and ISO strings
                timestamp = trade['timestamp']
                if hasattr(timestamp, 'isoformat'):
                    trade_copy['timestamp'] = timestamp.isoformat()
                elif isinstance(timestamp, str):
                    trade_copy['timestamp'] = timestamp
                else:
                    # Handle unexpected types
                    trade_copy['timestamp'] = str(timestamp)
                trade_data['trades'].append(trade_copy)
            except Exception as e:
                print(f"[BACKTEST] ⚠️  Error serializing trade {i}: {e}")
                print(f"[BACKTEST] Trade data: {trade}")
                # Continue processing other trades

        # Save to file
        try:
            with open(filename, 'w') as f:
                json.dump(trade_data, f, indent=2, default=str)
            print(f"[BACKTEST] 💾 Trades saved to: {filename}")
        except Exception as e:
            print(f"[BACKTEST] ❌ Error saving trades: {e}")

    def get_results(self) -> BacktestResult:
        """Calculate backtest performance metrics"""
        if not self.trades:
            return BacktestResult(
                symbol=self.symbol,
                start_time=self.start_datetime,
                end_time=self.end_datetime,
                config=self.config,
                total_trades=0,
                total_pnl=0.0,
                win_rate=0.0,
                max_position=0,
                final_position=0,
                trades=[],
                price_data=self.price_data
            )

        # Calculate P&L using simple mark-to-market approach
        if not self.price_data:
            total_pnl = 0.0
            position = 0
            max_pos = 0
        else:
            last_price = self.price_data[-1]['price']
            position = 0
            total_pnl = 0.0
            max_pos = 0

            # Calculate P&L for each trade against final price
            for trade in self.trades:
                if trade['action'] == 'BUY':
                    position += trade['quantity']
                    # Long: profit = final_price - buy_price
                    total_pnl += trade['quantity'] * (last_price - trade['price'])
                else:  # SELL
                    position -= trade['quantity']
                    # Short: profit = sell_price - final_price
                    total_pnl += trade['quantity'] * (trade['price'] - last_price)

                max_pos = max(max_pos, abs(position))

        # Calculate win rate (simplified)
        profitable_trades = 0
        for i, trade in enumerate(self.trades):
            if i < len(self.trades) - 1:
                next_trade = self.trades[i + 1]
                if trade['action'] == 'BUY' and next_trade['price'] > trade['price']:
                    profitable_trades += 1
                elif trade['action'] == 'SELL' and next_trade['price'] < trade['price']:
                    profitable_trades += 1

        win_rate = profitable_trades / len(self.trades) if self.trades else 0.0

        return BacktestResult(
            symbol=self.symbol,
            start_time=self.start_datetime,
            end_time=self.end_datetime,
            config=self.config,
            total_trades=len(self.trades),
            total_pnl=total_pnl,
            win_rate=win_rate,
            max_position=max_pos,
            final_position=position,
            trades=self.trades,
            price_data=self.price_data
        )

def backtest_fade(symbol: str, date: str, start_time: str, end_time: str, max_requests: int = 100, save_trades: bool = True, **config) -> BacktestResult:
    """
    Backtest fade strategy using historical IBKR data

    Args:
        symbol: Stock symbol (e.g., "TSLA")
        date: Date in YYYYMMDD format (e.g., "20250912")
        start_time: Start time in HH:MM format (e.g., "09:30")
        end_time: End time in HH:MM format (e.g., "10:30")
        **config: Strategy parameters (shares_per_dollar, min_move_threshold, etc.)

    Returns:
        BacktestResult with detailed performance metrics
    """

    # Default configuration - strategy parameters
    default_config = {
        'shares_per_dollar': 100,     # Number of shares to trade per $1 of excess move
        'min_move_threshold': 2.50,   # Minimum price move required to trigger trades ($)
        'time_window_minutes': 2.0,   # Rolling window for calculating price range (minutes)
        'max_position': 5000          # Maximum position size limit (shares)
    }
    default_config.update(config)

    # Format datetime strings for IBKR
    start_datetime = f"{date} {start_time}:00 US/Eastern"
    end_datetime = f"{date} {end_time}:00 US/Eastern"

    # Create backtest client
    client = BacktestClient(symbol, start_datetime, end_datetime, default_config)
    client.max_requests = max_requests  # Override max requests

    try:
        # Connect to IBKR
        client.connect('127.0.0.1', 4002, 7777)

        # Start API thread
        thread = threading.Thread(target=client.run, daemon=True)
        thread.start()

        # Wait for completion with reasonable timeout
        start_time = time.time()
        timeout = 120  # 2 minutes should be enough

        while not client.finished and (time.time() - start_time) < timeout:
            time.sleep(0.1)

        if not client.finished:
            print(f"[BACKTEST] No response after {timeout}s - likely no data available for this date/time")
            print(f"[BACKTEST] Try a different date or check your IBKR data permissions")
            client.disconnect()
            return None

        # Get results
        result = client.get_results()

        # Print summary
        print(f"\n📈 BACKTEST RESULTS")
        print(f"   Symbol: {result.symbol}")
        print(f"   Period: {date} {start_time}-{end_time}")
        print(f"   Trades: {result.total_trades}")
        print(f"   P&L: ${result.total_pnl:.2f}")
        print(f"   Win Rate: {result.win_rate:.1%}")
        print(f"   Max Position: {result.max_position} shares")
        print(f"   Final Position: {result.final_position} shares")
        print(f"   Price Ticks: {len(result.price_data)}")

        # JSON saving is now handled automatically at the end of the backtest

        return result

    except Exception as e:
        print(f"[BACKTEST] ❌ Error: {e}")
        return BacktestResult(
            symbol=symbol, start_time=start_datetime, end_time=end_datetime,
            config=default_config, total_trades=0, total_pnl=0.0, win_rate=0.0,
            max_position=0, final_position=0, trades=[], price_data=[]
        )

def quick_test():
    """Quick test function"""
    print("Quick Backtest Test")
    print("=" * 30)

    result = backtest_fade(
        symbol="TSLA",
        date="20250912",
        start_time="09:30",
        end_time="10:00",
        shares_per_dollar=50,
        min_move_threshold=0.75
    )

    if result.trades:
        print(f"\nFirst few trades:")
        for trade in result.trades[:3]:
            print(f"  {trade['timestamp'].strftime('%H:%M:%S')} {trade['action']} {trade['quantity']} @ ${trade['price']:.2f}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description='Backtest Fade Trading Strategy',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 backtest.py TSLA 20250915 09:30 09:50
  python3 backtest.py TSLA 20250915 09:30 09:50 --min-move-thresh 3.0 --shares-per-dollar 150
  python3 backtest.py TSLA 20250915 09:30 09:50 --time-window 1.5 --max-position 3000
        """
    )

    # Required positional arguments
    parser.add_argument('symbol', help='Stock symbol (e.g., TSLA)')
    parser.add_argument('date', help='Date in YYYYMMDD format (e.g., 20250915)')
    parser.add_argument('start_time', help='Start time in HH:MM format (e.g., 09:30)')
    parser.add_argument('end_time', help='End time in HH:MM format (e.g., 09:50)')

    # Optional strategy parameters
    parser.add_argument('--shares-per-dollar', type=float, default=100,
                       help='Number of shares to trade per $1 of excess move (default: 100)')
    parser.add_argument('--min-move-thresh', type=float, default=2.50,
                       help='Minimum price move required to trigger trades in $ (default: 2.50)')
    parser.add_argument('--time-window', type=float, default=2.0,
                       help='Rolling window for calculating price range in minutes (default: 2.0)')
    parser.add_argument('--max-position', type=int, default=5000,
                       help='Maximum position size limit in shares (default: 5000)')
    parser.add_argument('--max-requests', type=int, default=100,
                       help='Maximum number of IBKR data requests (default: 100)')

    args = parser.parse_args()

    print(f"Running backtest: {args.symbol} {args.date} {args.start_time}-{args.end_time}")
    print(f"Strategy params: shares_per_dollar={args.shares_per_dollar}, min_move_thresh=${args.min_move_thresh}, time_window={args.time_window}min, max_position={args.max_position}")

    result = backtest_fade(
        symbol=args.symbol,
        date=args.date,
        start_time=args.start_time,
        end_time=args.end_time,
        max_requests=args.max_requests,
        shares_per_dollar=args.shares_per_dollar,
        min_move_threshold=args.min_move_thresh,
        time_window_minutes=args.time_window,
        max_position=args.max_position
    )

    if result.trades:
        print(f"\nFirst few trades:")
        for trade in result.trades[:3]:
            print(f"  {trade['timestamp'].strftime('%H:%M:%S')} {trade['action']} {trade['quantity']} @ ${trade['price']:.2f}")