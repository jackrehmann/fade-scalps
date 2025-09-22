#!/usr/bin/env python3
"""
Multi-Parameter Testing and Optimization for Fade Trading System
Test different configurations simultaneously and find optimal parameters
"""

import json
from datetime import datetime
from typing import List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from backtest import backtest_fade, BacktestResult

class ParameterOptimizer:
    """Optimize fade trading parameters through systematic testing"""

    def __init__(self):
        self.results = []

    def parameter_sweep(self, symbol: str, date: str, start_time: str, end_time: str,
                       parameter_grid: Dict[str, List]) -> List[BacktestResult]:
        """
        Test all combinations of parameters

        Args:
            symbol: Stock symbol to test
            date: Date in YYYYMMDD format
            start_time: Start time in HH:MM format
            end_time: End time in HH:MM format
            parameter_grid: Dict of parameter names to lists of values to test

        Returns:
            List of BacktestResult objects, sorted by P&L
        """
        print(f"\n🔍 PARAMETER SWEEP")
        print(f"   Symbol: {symbol}")
        print(f"   Period: {date} {start_time}-{end_time}")
        print(f"   Parameter grid: {parameter_grid}")

        # Generate all parameter combinations
        configs = self._generate_configs(parameter_grid)
        print(f"   Total configurations to test: {len(configs)}")

        results = []

        # Test each configuration
        for i, config in enumerate(configs, 1):
            print(f"\n[{i}/{len(configs)}] Testing config: {config}")

            try:
                result = backtest_fade(symbol, date, start_time, end_time, **config)
                results.append(result)

                print(f"   Result: {result.total_trades} trades, ${result.total_pnl:.2f} P&L")

            except Exception as e:
                print(f"   Error: {e}")

        # Sort by P&L (best first)
        results.sort(key=lambda r: r.total_pnl, reverse=True)

        self._print_sweep_summary(results)
        return results

    def optimize_parameters(self, symbol: str, date: str, start_time: str, end_time: str,
                          optimization_target: str = "total_pnl") -> BacktestResult:
        """
        Find optimal parameters using a predefined search space

        Args:
            symbol: Stock symbol to optimize for
            date: Date to test on
            start_time: Start time
            end_time: End time
            optimization_target: Metric to optimize ("total_pnl", "win_rate", "total_trades")

        Returns:
            Best BacktestResult
        """
        print(f"\n🎯 PARAMETER OPTIMIZATION")
        print(f"   Optimizing for: {optimization_target}")

        # Define search space
        parameter_grid = {
            'shares_per_dollar': [50, 100, 150, 200],
            'min_move_threshold': [0.5, 1.0, 1.5, 2.0],
            'time_window_minutes': [1.0, 2.0, 3.0, 5.0]
        }

        results = self.parameter_sweep(symbol, date, start_time, end_time, parameter_grid)

        if not results:
            print("   ❌ No valid results found")
            return None

        # Find best result based on target metric
        if optimization_target == "win_rate":
            best_result = max(results, key=lambda r: r.win_rate)
        elif optimization_target == "total_trades":
            best_result = max(results, key=lambda r: r.total_trades)
        else:  # total_pnl
            best_result = results[0]  # Already sorted by P&L

        print(f"\n🏆 OPTIMAL PARAMETERS FOUND:")
        print(f"   Config: {best_result.config}")
        print(f"   Performance: {best_result.total_trades} trades, "
              f"${best_result.total_pnl:.2f} P&L, {best_result.win_rate:.1%} win rate")

        return best_result

    def multi_symbol_test(self, symbols: List[str], date: str, start_time: str, end_time: str,
                         config: Dict) -> Dict[str, BacktestResult]:
        """
        Test same configuration across multiple symbols

        Args:
            symbols: List of symbols to test
            date: Date to test
            start_time: Start time
            end_time: End time
            config: Configuration to test

        Returns:
            Dict mapping symbol to BacktestResult
        """
        print(f"\n📊 MULTI-SYMBOL TEST")
        print(f"   Symbols: {symbols}")
        print(f"   Period: {date} {start_time}-{end_time}")
        print(f"   Config: {config}")

        results = {}

        # Test each symbol with same config
        for symbol in symbols:
            print(f"\n   Testing {symbol}...")
            try:
                result = backtest_fade(symbol, date, start_time, end_time, **config)
                results[symbol] = result
                print(f"   {symbol}: {result.total_trades} trades, ${result.total_pnl:.2f} P&L")
            except Exception as e:
                print(f"   {symbol}: Error - {e}")

        # Print summary
        total_pnl = sum(r.total_pnl for r in results.values())
        total_trades = sum(r.total_trades for r in results.values())

        print(f"\n   📈 MULTI-SYMBOL SUMMARY:")
        print(f"   Total P&L: ${total_pnl:.2f}")
        print(f"   Total trades: {total_trades}")
        print(f"   Best performer: {max(results.keys(), key=lambda s: results[s].total_pnl)}")

        return results

    def parallel_test(self, test_configs: List[Tuple[str, str, str, str, Dict]],
                     max_workers: int = 3) -> List[BacktestResult]:
        """
        Run multiple backtests in parallel

        Args:
            test_configs: List of (symbol, date, start_time, end_time, config) tuples
            max_workers: Maximum parallel threads

        Returns:
            List of BacktestResult objects
        """
        print(f"\n⚡ PARALLEL TESTING")
        print(f"   Running {len(test_configs)} tests with {max_workers} workers")

        results = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tests
            future_to_config = {
                executor.submit(backtest_fade, symbol, date, start_time, end_time, **config):
                (symbol, date, start_time, end_time, config)
                for symbol, date, start_time, end_time, config in test_configs
            }

            # Collect results as they complete
            for future in as_completed(future_to_config):
                symbol, date, start_time, end_time, config = future_to_config[future]
                try:
                    result = future.result()
                    results.append(result)
                    print(f"   ✅ {symbol} {date}: {result.total_trades} trades, ${result.total_pnl:.2f}")
                except Exception as e:
                    print(f"   ❌ {symbol} {date}: Error - {e}")

        return results

    def save_results(self, results: List[BacktestResult], filename: str = "optimization_results.json"):
        """Save results to JSON file"""
        results_data = [asdict(result) for result in results]

        # Convert datetime objects to strings for JSON serialization
        for result in results_data:
            for trade in result['trades']:
                if 'timestamp' in trade and hasattr(trade['timestamp'], 'isoformat'):
                    trade['timestamp'] = trade['timestamp'].isoformat()

        with open(filename, 'w') as f:
            json.dump(results_data, f, indent=2, default=str)

        print(f"   💾 Results saved to {filename}")

    def _generate_configs(self, parameter_grid: Dict[str, List]) -> List[Dict]:
        """Generate all combinations of parameters"""
        import itertools

        keys = parameter_grid.keys()
        values = parameter_grid.values()

        configs = []
        for combination in itertools.product(*values):
            config = dict(zip(keys, combination))
            configs.append(config)

        return configs

    def _print_sweep_summary(self, results: List[BacktestResult]):
        """Print parameter sweep summary"""
        if not results:
            return

        print(f"\n📋 PARAMETER SWEEP SUMMARY")
        print(f"   Configurations tested: {len(results)}")

        # Top 5 results
        print(f"\n   🏆 TOP 5 CONFIGURATIONS:")
        for i, result in enumerate(results[:5], 1):
            print(f"   {i}. P&L: ${result.total_pnl:.2f}, Trades: {result.total_trades}, "
                  f"Win Rate: {result.win_rate:.1%}")
            print(f"      Config: {result.config}")

        # Statistics
        pnls = [r.total_pnl for r in results if r.total_trades > 0]
        if pnls:
            print(f"\n   📊 STATISTICS:")
            print(f"   Best P&L: ${max(pnls):.2f}")
            print(f"   Worst P&L: ${min(pnls):.2f}")
            print(f"   Average P&L: ${sum(pnls)/len(pnls):.2f}")
            print(f"   Profitable configs: {len([p for p in pnls if p > 0])}/{len(pnls)}")

# Simple functions for easy use

def find_best_config(symbol: str, date: str, start_time: str, end_time: str) -> Dict:
    """Find the best configuration for a symbol on a specific day"""
    optimizer = ParameterOptimizer()
    best_result = optimizer.optimize_parameters(symbol, date, start_time, end_time)
    return best_result.config if best_result else {}

def compare_configs(symbol: str, date: str, start_time: str, end_time: str,
                   configs: List[Dict]) -> List[BacktestResult]:
    """Compare multiple configurations on the same data"""
    results = []
    for i, config in enumerate(configs, 1):
        print(f"\n[{i}/{len(configs)}] Testing config {i}: {config}")
        result = backtest_fade(symbol, date, start_time, end_time, **config)
        results.append(result)

    # Sort by P&L
    results.sort(key=lambda r: r.total_pnl, reverse=True)

    print(f"\n🏆 CONFIGURATION COMPARISON:")
    for i, result in enumerate(results, 1):
        print(f"   {i}. ${result.total_pnl:.2f} P&L, {result.total_trades} trades - {result.config}")

    return results

def test_multiple_days(symbol: str, configs_and_dates: List[Tuple[Dict, str, str, str]]) -> List[BacktestResult]:
    """Test configurations across multiple days"""
    print(f"\n📅 MULTI-DAY TESTING for {symbol}")

    all_results = []
    for config, date, start_time, end_time in configs_and_dates:
        print(f"\n   Testing {date} {start_time}-{end_time} with {config}")
        result = backtest_fade(symbol, date, start_time, end_time, **config)
        all_results.append(result)

    # Summary across all days
    total_pnl = sum(r.total_pnl for r in all_results)
    total_trades = sum(r.total_trades for r in all_results)

    print(f"\n   📊 MULTI-DAY SUMMARY:")
    print(f"   Total P&L: ${total_pnl:.2f}")
    print(f"   Total trades: {total_trades}")
    print(f"   Average daily P&L: ${total_pnl/len(all_results):.2f}")

    return all_results

if __name__ == "__main__":
    # Example usage
    print("Parameter Optimization Example")
    print("=" * 35)

    # Find best parameters for TSLA on a specific day
    best_config = find_best_config("TSLA", "20250912", "09:30", "10:00")
    print(f"\nBest config found: {best_config}")

    # Compare a few specific configurations
    configs_to_test = [
        {"shares_per_dollar": 50, "min_move_threshold": 1.0},
        {"shares_per_dollar": 100, "min_move_threshold": 1.5},
        {"shares_per_dollar": 200, "min_move_threshold": 2.0}
    ]

    results = compare_configs("TSLA", "20250912", "09:30", "10:00", configs_to_test)