#!/usr/bin/env python3

"""
Agentic Trading LLM with Chart Tools
Simple daily chart tool for dynamic market analysis
"""

import os
import json
import requests
from datetime import datetime, timedelta
import pandas as pd
import matplotlib.pyplot as plt
import mplfinance as mpf
from openai import OpenAI

def load_api_keys():
    """Load API keys from .env file"""
    keys = {}
    try:
        with open('.env', 'r') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    keys[key] = value
    except FileNotFoundError:
        print("❌ .env file not found")
    return keys

def get_latest_trading_day():
    """Calculate the most recent trading day (excludes weekends)"""
    current_date = datetime.now()
    
    # If today is Monday-Friday, check if it's likely a trading day
    # If today is Saturday/Sunday, go back to Friday
    while current_date.weekday() >= 5:  # Saturday=5, Sunday=6
        current_date = current_date - timedelta(days=1)
    
    # For real-time systems, you might want to check market hours too
    # For now, assume any weekday is a trading day
    return current_date.strftime('%Y-%m-%d')

def get_daily_chart(ticker, start_date, end_date):
    """
    Generate daily candlestick chart for specified ticker and date range
    
    Args:
        ticker (str): Stock symbol (e.g., 'BABA', 'AAPL')
        start_date (str): Start date in YYYY-MM-DD format
        end_date (str): End date in YYYY-MM-DD format
    
    Returns:
        dict: Chart path and summary statistics
    """
    print(f"🔧 Generating daily chart for {ticker} ({start_date} to {end_date})")
    
    # Load API key
    keys = load_api_keys()
    api_key = keys.get('POLYGON_API_KEY')
    if not api_key:
        return {"error": "No Polygon API key found"}
    
    # Fetch daily data from Polygon
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start_date}/{end_date}"
    params = {
        'adjusted': 'true',
        'sort': 'asc',
        'apikey': api_key
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') != 'OK':
            return {"error": f"API Error: {data.get('status', 'Unknown')}"}
            
        results = data.get('results', [])
        if not results:
            return {"error": f"No data available for {ticker} in specified date range"}
        
        # Convert to DataFrame for charting
        data_list = []
        for bar in results:
            data_list.append({
                'Date': pd.to_datetime(datetime.fromtimestamp(bar['t'] / 1000)),
                'Open': bar['o'],
                'High': bar['h'],
                'Low': bar['l'],
                'Close': bar['c'],
                'Volume': bar['v']
            })
        
        df = pd.DataFrame(data_list)
        df.set_index('Date', inplace=True)
        df = df.sort_index()
        
        # Calculate summary stats
        first_price = results[0]['c']
        last_price = results[-1]['c']
        total_return = ((last_price - first_price) / first_price) * 100
        high_price = max(bar['h'] for bar in results)
        low_price = min(bar['l'] for bar in results)
        avg_volume = sum(bar['v'] for bar in results) / len(results)
        
        # Generate chart
        chart_path = f"/tmp/{ticker}_{start_date}_{end_date}_daily.png"
        
        # Configure chart style
        mc = mpf.make_marketcolors(
            up='green',
            down='red',
            edge='black',
            wick={'up': 'green', 'down': 'red'},
            volume='blue'
        )
        
        style = mpf.make_mpf_style(
            marketcolors=mc,
            gridstyle='-',
            y_on_right=False
        )
        
        # Create chart
        title = f'{ticker}: {start_date} to {end_date} ({total_return:+.1f}%)'
        mpf.plot(
            df,
            type='candle',
            style=style,
            title=title,
            ylabel='Price ($)',
            volume=True,
            savefig=chart_path,
            figsize=(14, 8),
            tight_layout=True
        )
        
        # Return results
        return {
            "chart_path": chart_path,
            "ticker": ticker,
            "start_date": start_date,
            "end_date": end_date,
            "days": len(results),
            "first_price": round(first_price, 2),
            "last_price": round(last_price, 2),
            "total_return_pct": round(total_return, 2),
            "high_price": round(high_price, 2),
            "low_price": round(low_price, 2),
            "price_range_pct": round(((high_price - low_price) / low_price) * 100, 2),
            "avg_daily_volume": int(avg_volume),
            "summary": f"{ticker} moved {total_return:+.1f}% over {len(results)} days from ${first_price:.2f} to ${last_price:.2f}"
        }
        
    except Exception as e:
        return {"error": f"Failed to fetch data: {str(e)}"}

# OpenAI Function Schema
DAILY_CHART_FUNCTION = {
    "name": "get_daily_chart",
    "description": "Generate a daily candlestick chart for a stock ticker over a specified date range. Returns chart image and summary statistics.",
    "parameters": {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock symbol (e.g., 'BABA', 'AAPL', 'TSLA')"
            },
            "start_date": {
                "type": "string", 
                "description": "Start date in YYYY-MM-DD format (e.g., '2024-01-01')"
            },
            "end_date": {
                "type": "string",
                "description": "End date in YYYY-MM-DD format (e.g., '2024-12-31')"
            }
        },
        "required": ["ticker", "start_date", "end_date"]
    }
}

class AgenticTrader:
    """Simple agentic trading assistant with chart tools"""
    
    def __init__(self):
        keys = load_api_keys()
        openai_key = keys.get('OPENAI_API_KEY')
        if not openai_key:
            raise ValueError("No OpenAI API key found in .env file")
        
        self.client = OpenAI(api_key=openai_key)
        self.tools = [{"type": "function", "function": DAILY_CHART_FUNCTION}]
        
    def chat(self, user_message):
        """Handle a chat message with tool calling capability"""
        
        # Calculate dates dynamically
        today = datetime.now()
        latest_trading_day = get_latest_trading_day()
        current_year = today.year
        
        messages = [
            {
                "role": "system",
                "content": f"""You are an expert trading analyst with access to chart generation tools.

Today's date is {today.strftime('%B %d, %Y')} ({today.strftime('%Y-%m-%d')}).
Latest trading day: {latest_trading_day}

You can generate daily stock charts for any ticker and date range to help analyze market patterns, trends, and trading opportunities.

When users ask about stock performance, price movements, or want to see charts, use the get_daily_chart tool to get numerical data and chart files.

IMPORTANT: When interpreting time references, use these precise dates:
- "recent" or "recently" = last 30-60 days ending on {latest_trading_day}
- "this week" = current week ending on {latest_trading_day}
- "this month" = current month ending on {latest_trading_day}
- "this year" or "YTD" = January 1, {current_year} to {latest_trading_day}
- "last month" = previous month from today
- "last quarter" = previous 3 months from today

Always use {latest_trading_day} as the end date for "current" or "recent" requests to ensure you get the most up-to-date market data available.

Analyze the numerical data to provide insights about trends, volatility, volume patterns, and trading opportunities. Charts are saved as files for reference."""
            },
            {
                "role": "user", 
                "content": user_message
            }
        ]
        
        # Initial LLM call
        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=self.tools,
            tool_choice="auto"
        )
        
        response_message = response.choices[0].message
        
        # Handle tool calls if any
        if response_message.tool_calls:
            messages.append(response_message)
            
            # Execute each tool call
            for tool_call in response_message.tool_calls:
                if tool_call.function.name == "get_daily_chart":
                    # Parse arguments
                    args = json.loads(tool_call.function.arguments)
                    
                    # Execute tool
                    result = get_daily_chart(
                        ticker=args["ticker"],
                        start_date=args["start_date"], 
                        end_date=args["end_date"]
                    )
                    
                    # Add tool result to messages
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result)
                    })
            
            # Get final response from LLM
            final_response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages
            )
            
            return final_response.choices[0].message.content
        
        else:
            return response_message.content

def main():
    """Simple CLI interface"""
    print("🤖 Agentic Trader - Daily Chart Analysis")
    print("=" * 50)
    
    try:
        trader = AgenticTrader()
        
        while True:
            user_input = input("\n💬 Ask me about stocks (or 'quit' to exit): ")
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("👋 Goodbye!")
                break
                
            if user_input.strip():
                print("\n🤖 Analyzing...")
                response = trader.chat(user_input)
                print(f"\n📊 Analysis:\n{response}")
                
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()