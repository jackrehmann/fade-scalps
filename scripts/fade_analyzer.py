#!/usr/bin/env python3

import json
import requests
import os
import time
from datetime import datetime, timedelta
from openai import OpenAI

# Configuration
POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')
STOCKTWITS_API_URL = 'https://api.stocktwits.com/api/2/trending/symbols.json'
YAHOO_TRENDING_URL = 'https://query1.finance.yahoo.com/v1/finance/trending/US?count=15'
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
RESULTS_FILE = 'results.json'
CACHE_FILE = 'historical_cache.json'

class FadeAnalyzer:
    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY)
    
    def get_trading_days(self, days_back=125):
        """Get list of trading days, excluding weekends"""
        trading_days = []
        current_date = datetime.now()
        
        while len(trading_days) < days_back:
            # Skip weekends (Monday=0, Sunday=6)
            if current_date.weekday() < 5:  # Monday-Friday
                trading_days.append(current_date.strftime('%Y-%m-%d'))
            current_date -= timedelta(days=1)
        
        return trading_days
        
    def get_yahoo_trending(self):
        """Fetch trending tickers from Yahoo Finance"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            
            response = requests.get(YAHOO_TRENDING_URL, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            tickers = []
            if 'finance' in data and 'result' in data['finance']:
                result = data['finance']['result'][0] if data['finance']['result'] else {}
                if 'quotes' in result:
                    for quote in result['quotes']:
                        ticker = quote.get('symbol', '')
                        
                        # Filter out crypto, forex, indices
                        if '-USD' in ticker or '=F' in ticker or '^' in ticker:
                            continue
                        if 'BTC' in ticker or 'ETH' in ticker or 'USD' in ticker:
                            continue
                        
                        # Keep standard equity tickers
                        if len(ticker) <= 5 and ticker.isalpha() and ticker.isupper():
                            tickers.append(ticker)
            
            return tickers[:10]  # Return up to 10 tickers
            
        except Exception as e:
            print(f"Error fetching Yahoo trending: {e}")
            return []
    
    def get_stocktwits_trending(self):
        """Fetch trending tickers from Stocktwits"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(STOCKTWITS_API_URL, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            tickers = []
            for symbol_data in data.get('symbols', []):
                ticker = symbol_data['symbol']
                
                # Skip crypto, forex, and other non-equity symbols
                if '.' in ticker or '-' in ticker or len(ticker) > 5:
                    continue
                    
                # Skip obvious crypto/token indicators
                if any(crypto_word in ticker.upper() for crypto_word in ['BTC', 'ETH', 'DOGE', 'SHIB']):
                    continue
                
                # Keep standard equity tickers
                if len(ticker) <= 4 and ticker.isalpha() and ticker.isupper():
                    tickers.append(ticker)
                
                if len(tickers) >= 10:
                    break
            
            return tickers
            
        except Exception as e:
            print(f"Error fetching Stocktwits trending: {e}")
            return []
    
    def get_trending_tickers(self):
        """Get trending tickers from Yahoo Finance (pure retail focus)"""
        
        print("Fetching trending tickers from Yahoo Finance...")
        
        # Get trending from Yahoo Finance (most searched by retail)
        yahoo_tickers = self.get_yahoo_trending()
        print(f"Yahoo Finance trending: {yahoo_tickers}")
        
        # Use ALL trending names - no fallbacks, pure retail
        final_tickers = []
        
        for ticker in yahoo_tickers:
            if ticker not in final_tickers:
                final_tickers.append(ticker)
            if len(final_tickers) >= 8:  # Get top 8 pure trending
                break
        
        print(f"Final ticker list: {final_tickers}")
        print("✅ Pure retail trending - no liquid fallbacks")
        
        return final_tickers
    
    def get_stock_data(self, symbol):
        """Fetch intraday and daily data for a symbol using Polygon.io"""
        # Get trading days
        trading_days = self.get_trading_days(125)
        today = trading_days[0]  # Most recent trading day
        start_date = trading_days[-1]  # 125 days back
        
        # 1-minute aggregates for today
        intraday_url = f'https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/{today}/{today}?adjusted=true&sort=asc&apikey={POLYGON_API_KEY}'
        
        # Daily data for last 125 trading days
        daily_url = f'https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{start_date}/{today}?adjusted=true&sort=asc&apikey={POLYGON_API_KEY}'
        
        try:
            # Get intraday data
            intraday_response = requests.get(intraday_url, timeout=30)
            intraday_response.raise_for_status()
            intraday_data = intraday_response.json()
            
            # Check for API error
            if intraday_data.get('status') != 'OK':
                print(f"Polygon error for {symbol}: {intraday_data.get('error', 'Unknown error')}")
                return None
            
            # Get daily data
            daily_response = requests.get(daily_url, timeout=30)
            daily_response.raise_for_status()
            daily_data = daily_response.json()
            
            # Check for API error
            if daily_data.get('status') != 'OK':
                print(f"Polygon error for {symbol}: {daily_data.get('error', 'Unknown error')}")
                return None
            
            return {
                'symbol': symbol,
                'intraday': intraday_data.get('results', []),
                'daily': daily_data.get('results', [])
            }
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            return None
    
    def load_cache(self):
        """Load cached historical data"""
        try:
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def save_cache(self, cache_data):
        """Save historical data to cache"""
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache_data, f, indent=2)
    
    def get_historical_first_90min_data(self, symbol, days_back=20):
        """Fetch first 90-minute data for the last 20 trading days (with caching)"""
        # Load existing cache
        cache = self.load_cache()
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Check if we have recent data for this symbol
        cache_key = f"{symbol}_first_90min"
        if cache_key in cache and cache[cache_key].get('last_updated') == today:
            print(f"Using cached first 90-minute data for {symbol}")
            return cache[cache_key]['data']
        
        # Fetch fresh data
        trading_days = self.get_trading_days(days_back)
        historical_data = {}
        
        print(f"Fetching {days_back}-day first 90-minute history for {symbol}...")
        
        for i, date in enumerate(trading_days):
            try:
                # Get 1-minute data for this specific day
                url = f'https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/{date}/{date}?adjusted=true&sort=asc&apikey={POLYGON_API_KEY}'
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                if data.get('status') == 'OK' and data.get('results'):
                    first_90min_stats = self.calculate_first_90min_stats(data['results'])
                    if first_90min_stats:
                        historical_data[date] = first_90min_stats
                
                # Rate limiting - be respectful
                time.sleep(0.2)
                
                if i % 5 == 0:
                    print(f"  Processed {i+1}/{len(trading_days)} days...")
                    
            except Exception as e:
                print(f"Error fetching {symbol} data for {date}: {e}")
                continue
        
        # Cache the results
        cache[cache_key] = {
            'last_updated': today,
            'data': historical_data
        }
        self.save_cache(cache)
        
        print(f"  Collected first 90-minute data for {len(historical_data)} days")
        return historical_data
    
    def calculate_first_90min_stats(self, intraday_data):
        """Calculate first 90 minutes price action statistics using Polygon data"""
        if not intraday_data:
            return None
            
        # Filter for first 90 minutes (9:30 AM - 11:00 AM EST)
        # Polygon timestamps are in milliseconds since epoch
        first_90min_bars = []
        
        for bar in intraday_data:
            # Convert timestamp from milliseconds to datetime
            bar_time = datetime.fromtimestamp(bar['t'] / 1000)
            hour = bar_time.hour
            minute = bar_time.minute
            
            # Check if within first 90 minutes (9:30 AM - 11:00 AM)
            if (hour == 9 and minute >= 30) or (hour == 10) or (hour == 11 and minute == 0):
                first_90min_bars.append(bar)
        
        if not first_90min_bars:
            return None
            
        # Sort by timestamp to ensure chronological order
        first_90min_bars.sort(key=lambda x: x['t'])
        
        # Calculate stats using Polygon's OHLC format
        # o=open, h=high, l=low, c=close
        open_price = first_90min_bars[0]['o']
        current_price = first_90min_bars[-1]['c']
        
        return {
            'open_price': open_price,
            'current_price': current_price,
            'price_change': current_price - open_price,
            'percent_change': ((current_price - open_price) / open_price) * 100,
            'high': max(bar['h'] for bar in first_90min_bars),
            'low': min(bar['l'] for bar in first_90min_bars),
            'volume': sum(bar['v'] for bar in first_90min_bars),
            'num_bars': len(first_90min_bars)
        }
    
    def load_historical_results(self):
        """Load previous analysis results"""
        try:
            with open(RESULTS_FILE, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return []
    
    def save_results(self, results):
        """Save analysis results to file"""
        historical_results = self.load_historical_results()
        historical_results.append(results)
        
        # Keep only last 30 days
        if len(historical_results) > 30:
            historical_results = historical_results[-30:]
        
        with open(RESULTS_FILE, 'w') as f:
            json.dump(historical_results, f, indent=2)
    
    def calculate_daily_volatility(self, daily_data):
        """Calculate 20-day volatility from daily OHLC data"""
        if len(daily_data) < 20:
            return None
        
        # Calculate daily returns from close prices
        returns = []
        for i in range(1, min(21, len(daily_data))):
            prev_close = daily_data[i-1]['c']
            curr_close = daily_data[i]['c']
            daily_return = (curr_close - prev_close) / prev_close
            returns.append(daily_return)
        
        # Calculate volatility (standard deviation * sqrt(252))
        import math
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
        volatility = math.sqrt(variance) * math.sqrt(252)  # Annualized
        
        return round(volatility, 4)
    
    def create_simple_data_table(self, symbol, data):
        """Create a simple data table - no analysis, just raw data"""
        history = data['first_90min_history']
        if not history:
            return f"{symbol}: No historical data available"
        
        # Sort by date (most recent first)
        sorted_dates = sorted(history.keys(), reverse=True)
        
        summary_lines = [f"\n📊 {symbol} - Last 5 Days First 90min Data:"]
        summary_lines.append("Date        | Move    | Volume")
        summary_lines.append("------------|---------|----------")
        
        for date in sorted_dates[:5]:  # Show last 5 days
            stats = history[date]
            move = stats['percent_change']
            volume = stats.get('volume', 0)
            volume_str = f"{volume/1000:.0f}K" if volume > 0 else "N/A"
            summary_lines.append(f"{date} | {move:+5.1f}% | {volume_str:>8s}")
        
        return "\n".join(summary_lines)
    
    def create_simple_chart(self, symbol, history):
        """Create a simple ASCII chart of first 90-minute moves"""
        if not history:
            return f"No data for {symbol}"
        
        # Get last 5 days for chart
        sorted_dates = sorted(history.keys(), reverse=True)[:5]
        moves = [history[date]['percent_change'] for date in sorted_dates]
        
        chart_lines = [f"\n📈 {symbol} First 90min Chart (Last 5 Days):"]
        
        # Find range for scaling
        max_move = max(abs(m) for m in moves) if moves else 1
        scale = max(6, int(max_move) + 1)
        
        # Create ASCII chart
        for level in range(scale, -scale-1, -1):
            line = f"{level:+2d}% |"
            for move in moves:
                if abs(move - level) < 0.5:
                    line += "■"
                elif level == 0:
                    line += "-"
                else:
                    line += " "
            chart_lines.append(line)
        
        # Add date labels (abbreviated)
        date_line = "     "
        for date in sorted_dates:
            date_line += date[-2:]  # Last 2 digits of day
        chart_lines.append(date_line)
        
        return "\n".join(chart_lines)
    
    def analyze_with_llm(self, market_data, historical_results):
        """Use LLM with human-like analysis approach"""
        
        # Create simple data tables and charts for each stock
        data_summaries = []
        for symbol, data in market_data.items():
            table = self.create_simple_data_table(symbol, data)
            chart = self.create_simple_chart(symbol, data['first_90min_history'])
            data_summaries.append(f"{table}\n{chart}\n")
        
        # Today's action
        today_summary = []
        for symbol, data in market_data.items():
            today = data['today']
            move = today['percent_change']
            volume = today.get('volume', 0)
            volume_str = f"{volume/1000:.0f}K" if volume > 0 else "N/A"
            today_summary.append(f"   • {symbol}: {move:+.1f}% (Vol: {volume_str})")
        
        prompt = f"""
Here's the raw data for today's first 90 minutes and historical patterns:

TODAY'S MOVES:
{''.join(today_summary)}

RAW DATA & CHARTS:
{''.join(data_summaries)}

Question: Which stocks should we fade and at what threshold?

Respond in JSON:
{{
    "fade_threshold_percent": <number>,
    "recommended_symbols": [<symbols>],
    "confidence": <1-10>,
    "reasoning": "<brief explanation>"
}}
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"Error with LLM analysis: {e}")
            return None
    
    def run_analysis(self):
        """Main analysis function"""
        print(f"Starting fade analysis for {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Get trending tickers
        trending_tickers = self.get_trending_tickers()
        print(f"Analyzing trending tickers: {trending_tickers}")
        
        # Fetch market data with historical context
        market_data = {}
        for ticker in trending_tickers:
            print(f"Fetching data for {ticker}...")
            
            # Get today's data
            stock_data = self.get_stock_data(ticker)
            if not stock_data:
                continue
                
            # Get today's first 90-minute stats
            first_90min_stats = self.calculate_first_90min_stats(stock_data['intraday'])
            if not first_90min_stats:
                continue
            
            # Get historical first 90-minute data
            historical_first_90min = self.get_historical_first_90min_data(ticker)
            
            market_data[ticker] = {
                'today': first_90min_stats,
                'daily_history': stock_data['daily'],
                'first_90min_history': historical_first_90min
            }
            
            print(f"  Today: {first_90min_stats['percent_change']:.2f}% move")
            print(f"  Historical context: {len(historical_first_90min)} days, {len(stock_data['daily'])} daily bars")
            
            # Small delay to be respectful to API
            time.sleep(0.1)
        
        if not market_data:
            print("No market data available for analysis")
            return
        
        print(f"Market data collected for {len(market_data)} symbols")
        
        # Load historical results
        historical_results = self.load_historical_results()
        
        # Analyze with LLM
        llm_analysis = self.analyze_with_llm(market_data, historical_results)
        
        if llm_analysis:
            # Prepare final results
            results = {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'timestamp': datetime.now().isoformat(),
                'market_data': market_data,
                'llm_analysis': llm_analysis
            }
            
            # Save results
            self.save_results(results)
            
            print("\n🎯 FADE ANALYSIS COMPLETE!")
            print("="*60)
            print(f"💡 AI Recommendation:")
            print(f"   Fade threshold: {llm_analysis['fade_threshold_percent']}%")
            print(f"   Best symbols: {', '.join(llm_analysis['recommended_symbols'])}")
            print(f"   Confidence: {llm_analysis['confidence']}/10")
            
            print(f"\n🧠 AI Reasoning:")
            reasoning = llm_analysis['reasoning']
            # Break up long reasoning into readable chunks
            import textwrap
            wrapped_reasoning = textwrap.fill(reasoning, width=80, initial_indent='   ', subsequent_indent='   ')
            print(wrapped_reasoning)
            
            print(f"\n📊 Data Summary:")
            for symbol, data in market_data.items():
                today_move = data['today']['percent_change']
                hist_days = len(data['first_90min_history'])
                status = "✅" if symbol in llm_analysis['recommended_symbols'] else "➖"
                print(f"  {status} {symbol}: {today_move:+.1f}% today ({hist_days} days analyzed)")
        else:
            print("LLM analysis failed")
    
    def test_api_connection(self):
        """Test API connections without full analysis"""
        print("Testing API connections...")
        
        # Test Stocktwits
        print("Testing Stocktwits...")
        tickers = self.get_trending_tickers()
        print(f"Trending tickers: {tickers[:3]}")
        
        # Test Polygon with one ticker
        print("Testing Polygon.io...")
        if tickers:
            test_data = self.get_stock_data(tickers[0])
            if test_data:
                print(f"Successfully fetched data for {tickers[0]}")
                print(f"Intraday data points: {len(test_data['intraday'])}")
                print(f"Daily data points: {len(test_data['daily'])}")
                if test_data['intraday']:
                    first_bar = test_data['intraday'][0]
                    bar_time = datetime.fromtimestamp(first_bar['t'] / 1000)
                    print(f"First bar time: {bar_time}")
                    print(f"First bar OHLC: O={first_bar['o']}, H={first_bar['h']}, L={first_bar['l']}, C={first_bar['c']}")
            else:
                print(f"Failed to fetch data for {tickers[0]}")
        
        # Test OpenAI
        print("Testing OpenAI...")
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": "Reply with 'API test successful'"}],
                temperature=0
            )
            print(f"OpenAI response: {response.choices[0].message.content}")
        except Exception as e:
            print(f"OpenAI test failed: {e}")

if __name__ == "__main__":
    if not POLYGON_API_KEY or not OPENAI_API_KEY:
        print("Error: Please set POLYGON_API_KEY and OPENAI_API_KEY environment variables")
        exit(1)
    
    analyzer = FadeAnalyzer()
    
    # Check for test mode
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        analyzer.test_api_connection()
    else:
        analyzer.run_analysis()