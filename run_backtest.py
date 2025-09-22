#!/usr/bin/env python3
"""
Convenience script to run backtests from root directory
"""
import sys
import os

# Add src directory to Python path
src_path = os.path.join(os.path.dirname(__file__), 'src')
sys.path.insert(0, src_path)

# Change to src directory so relative imports work
original_cwd = os.getcwd()
os.chdir(src_path)

try:
    # Import and run backtest
    import backtest
    # Run the main section
    if hasattr(backtest, '__main__') or '__main__' in sys.modules:
        exec(open('backtest.py').read())
finally:
    # Restore original directory
    os.chdir(original_cwd)