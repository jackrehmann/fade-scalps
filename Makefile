.PHONY: help live backtest plot clean install test

# Default target
help:
	@echo "Fade Trading System - Available Commands:"
	@echo ""
	@echo "  make live SYMBOL=TSLA [OPTIONS]     - Run live trading"
	@echo "  make backtest SYMBOL=TSLA DATE=20250918 START=09:30 END=10:30 [OPTIONS]"
	@echo "  make plot FILE=results/backtests/backtest_TSLA_*.json"
	@echo "  make clean                          - Clean up generated files"
	@echo "  make install                        - Install dependencies"
	@echo "  make test                          - Run quick tests"
	@echo ""
	@echo "Live Trading Examples:"
	@echo "  make live SYMBOL=TSLA                    # Simulation mode"
	@echo "  make live SYMBOL=TSLA MODE=ibkr          # Send to IBKR"
	@echo "  make live SYMBOL=TSLA MODE=ibkr THRESH=1.0 SHARES=150"
	@echo "  make live SYMBOL=TSLA END_TIME=10:30     # Auto-stop and flatten"
	@echo "  make live SYMBOL=\"TSLA AAPL\" MODE=ibkr  # Multiple symbols"
	@echo ""
	@echo "Backtest Examples:"
	@echo "  make backtest SYMBOL=TSLA DATE=20250918 START=09:30 END=10:30"
	@echo "  make backtest SYMBOL=TSLA DATE=20250918 START=09:30 END=10:30 THRESH=1.0 DELAY=12"
	@echo ""
	@echo "Plot Examples:"
	@echo "  make plot FILE=results/backtests/backtest_TSLA_20250918_0930-1030.json"
	@echo "  make plot-latest SYMBOL=TSLA            # Plot most recent backtest"

# Variables with defaults
SYMBOL ?= TSLA
MODE ?= simulate
THRESH ?= 1.50
SHARES ?= 100
WINDOW ?= 2.0
POSITION ?= 5000
END_TIME ?=

DATE ?= 20250918
START ?= 09:30
END ?= 10:30
DELAY ?= 0.0
REQUESTS ?= 100

# Live trading
live:
	@echo "🚀 Starting live trading for $(SYMBOL)..."
ifeq ($(MODE),ibkr)
	python3 run_live.py $(SYMBOL) --send-to-ibkr --min-move-thresh $(THRESH) --shares-per-dollar $(SHARES) --time-window $(WINDOW) --max-position $(POSITION) $(if $(END_TIME),--end-time $(END_TIME))
else
	python3 run_live.py $(SYMBOL) --simulate-only --min-move-thresh $(THRESH) --shares-per-dollar $(SHARES) --time-window $(WINDOW) --max-position $(POSITION) $(if $(END_TIME),--end-time $(END_TIME))
endif

# Backtesting
backtest:
	@echo "📊 Running backtest for $(SYMBOL) on $(DATE) $(START)-$(END)..."
	python3 run_backtest.py $(SYMBOL) $(DATE) $(START) $(END) --min-move-thresh $(THRESH) --shares-per-dollar $(SHARES) --time-window $(WINDOW) --max-position $(POSITION) --delay $(DELAY) --max-requests $(REQUESTS)

# Plotting
plot:
ifndef FILE
	@echo "❌ Error: FILE parameter required"
	@echo "Usage: make plot FILE=results/backtests/backtest_TSLA_*.json"
	@exit 1
endif
	@echo "📈 Plotting trades from $(FILE)..."
	python3 run_plot.py $(FILE)

# Plot most recent backtest for a symbol
plot-latest:
	@echo "📈 Finding most recent backtest for $(SYMBOL)..."
	@LATEST=$$(ls -t results/backtests/backtest_$(SYMBOL)_*.json 2>/dev/null | head -1); \
	if [ -z "$$LATEST" ]; then \
		echo "❌ No backtest files found for $(SYMBOL)"; \
		exit 1; \
	else \
		echo "📈 Plotting $$LATEST..."; \
		python3 run_plot.py $$LATEST; \
	fi

# Quick TSLA test for tomorrow
tsla-tomorrow:
	@echo "🎯 TSLA First Hour Test (9:30-10:30 AM)"
	python3 run_live.py TSLA --send-to-ibkr --min-move-thresh 1.50 --shares-per-dollar 100 --end-time 10:30

# Development helpers
install:
	@echo "📦 Installing dependencies..."
	pip3 install -r requirements.txt

clean:
	@echo "🧹 Cleaning up..."
	rm -rf __pycache__ src/__pycache__ scripts/__pycache__
	find . -name "*.pyc" -delete
	@echo "✅ Cleaned up cache files"

clean-results:
	@echo "🧹 Cleaning results (WARNING: This will delete all backtest data)..."
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		rm -rf results/backtests/* results/charts/*; \
		echo "✅ Results cleaned"; \
	else \
		echo "❌ Cancelled"; \
	fi

# Quick tests
test:
	@echo "🧪 Running quick tests..."
	@echo "Testing imports..."
	python3 -c "import sys; sys.path.insert(0, 'src'); from src.fade_trader import FadeEngine; print('✅ FadeEngine import OK')"
	python3 -c "import sys; sys.path.insert(0, 'src'); from src.live_trader import LiveTradingClient; print('✅ LiveTrader import OK')"
	python3 -c "import sys; sys.path.insert(0, 'src'); from src.backtest import backtest_fade; print('✅ Backtest import OK')"
	@echo "✅ All imports working"

# Show current directory structure
structure:
	@echo "📁 Current project structure:"
	@find . -type d | grep -v -E "__pycache__|\.git|fade_engine|tws_build" | sort | sed 's/^/  /'

# Show recent results
results:
	@echo "📊 Recent backtest results:"
	@ls -lt results/backtests/*.json 2>/dev/null | head -5 | awk '{print "  " $$9 " (" $$6 " " $$7 " " $$8 ")"}'
	@echo ""
	@echo "📈 Recent charts:"
	@ls -lt results/charts/*.png 2>/dev/null | head -5 | awk '{print "  " $$9 " (" $$6 " " $$7 " " $$8 ")"}'

# Show logs
logs:
	@echo "📝 Recent log entries:"
	@tail -20 logs/fade_trader.log 2>/dev/null || echo "No logs found"

# Development workflow shortcuts
dev-setup: install test
	@echo "🎯 Development environment ready!"

# Market hours reminder
market-hours:
	@echo "⏰ US Market Hours (ET):"
	@echo "  Regular: 9:30 AM - 4:00 PM"
	@echo "  Pre-market: 4:00 AM - 9:30 AM"
	@echo "  After-hours: 4:00 PM - 8:00 PM"
	@echo ""
	@echo "Current time: $$(date)"