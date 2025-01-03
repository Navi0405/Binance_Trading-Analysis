import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from django.shortcuts import render
from plotly.subplots import make_subplots

def fetch_binance_candlestick_data(symbol, start_time, end_time):
    # Convert the start_time and end_time to Unix timestamps (milliseconds)
    start_timestamp = int(datetime.strptime(start_time, '%Y-%m-%d').timestamp() * 1000)
    end_timestamp = int(datetime.strptime(end_time, '%Y-%m-%d').timestamp() * 1000)

    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=4h&startTime={start_timestamp}&endTime={end_timestamp}&limit=1000"
    response = requests.get(url)
    data = response.json()

    # Check if the data is empty or invalid
    if not data:
        return []

    # Parse the data into a pandas DataFrame
    df = pd.DataFrame(data)
    df = df.iloc[:, :6]  # Keep only the first 6 columns (Time, Open, High, Low, Close, Volume)
    df.columns = ['Time', 'Open', 'High', 'Low', 'Close', 'Volume']
    df['Time'] = pd.to_datetime(df['Time'], unit='ms')  # Convert Time from milliseconds to datetime

    # Convert only the numeric columns to float
    numeric_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    df[numeric_columns] = df[numeric_columns].astype(float)

    return df.to_dict(orient='records')  # Return the data as a list of dictionaries


def load_trade_data_from_csv(filepath, window_size):
    # Load the CSV file
    df = pd.read_csv(filepath)

    # Ensure the date columns are parsed as datetime with the correct format
    df['entry_dt'] = pd.to_datetime(df['entry_dt'], format='%Y-%m-%d %H:%M:%S')
    df['exit_dt'] = pd.to_datetime(df['exit_dt'], format='%Y-%m-%d %H:%M:%S')

    # Determine position type: 1 for LONG, -1 for SHORT, 0 for MIXED
    df['position_type'] = df['qty'].apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)).astype(int)

    # Apply the rolling window_size on 'position_type' and rename it to 'uniformity'
    df['uniformity'] = df['position_type'].rolling(window_size).apply(
        lambda x: 1 if (x == 1).all() else (-1 if (x == -1).all() else 0), raw=False
    )


    return df


def generate_chart_from_data(trades_df, symbol, window_size):
    # Check if the necessary columns exist in the DataFrame
    required_columns = ['entry_dt', 'entry_price', 'exit_price', 'position_type']
    for col in required_columns:
        if col not in trades_df.columns:
            raise ValueError(f"Missing required column: {col}")

    # Create a single chart with multiple Y-axes
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Add candlestick trace (left Y-axis)
    fig.add_trace(
        go.Candlestick(
            x=trades_df['entry_dt'],
            open=trades_df['entry_price'],
            high=trades_df['entry_price'].combine(trades_df['exit_price'], max),
            low=trades_df['entry_price'].combine(trades_df['exit_price'], min),
            close=trades_df['exit_price'],
            name="Candlesticks in Price"
        ),
        secondary_y=False  # Attach to the left Y-axis
    )

    # Calculate LONG and SHORT counts for each rolling window
    trades_df['long_count'] = trades_df['position_type'].rolling(window_size).apply(lambda x: (x == 1).sum(), raw=False)
    trades_df['short_count'] = trades_df['position_type'].rolling(window_size).apply(lambda x: (x == -1).sum(), raw=False)

    # Calculate the difference between LONG and SHORT counts for each window
    trades_df['position_diff'] = trades_df['long_count'] - trades_df['short_count']

    # Add LONG - SHORT Difference scatter trace (right Y-axis)
    fig.add_trace(
        go.Scatter(
            x=trades_df['entry_dt'],
            y=trades_df['position_diff'],
            mode="lines",
            line=dict(color="blue", width=2),
            name="LONG - SHORT in Price"
        ),
        secondary_y=True  # Attach to the right Y-axis
    )

    # Calculate the LONG/SHORT ratio
    trades_df['long_short_ratio'] = trades_df['long_count'] / (trades_df['long_count'] + trades_df['short_count'] + 1e-10)

    # Add LONG/SHORT Ratio scatter trace (right Y-axis)
    fig.add_trace(
        go.Scatter(
            x=trades_df['entry_dt'],
            y=trades_df['long_short_ratio'],
            mode="lines",
            line=dict(color="purple", width=2, dash="dot"),
            name="LONG/SHORT Ratio in Price"
        ),
        secondary_y=True  # Attach to the right Y-axis
    )

    # Update layout for better visualization
    fig.update_layout(
        title=f"Candlestick and Position Analysis for {symbol}",
        xaxis_title="Date",
        yaxis_title="Price (Candlestick)",  # Left Y-axis title
        yaxis2_title="Price (Trades in Quantity)",  # Right Y-axis title
        template="plotly_dark",
        legend_title="Indicators",
        height=600  # Adjust height
    )

    return fig.to_html(full_html=False)

def account_trades_view(request):
    # Set up parameters
    symbol = request.GET.get('symbol', 'BTCUSDT')
    start_date = request.GET.get('start_date', datetime.now().replace(day=1).strftime('%Y-%m-%d'))
    end_date = request.GET.get('end_date', datetime.now().strftime('%Y-%m-%d'))
    window_size = int(request.GET.get('window_size', 20))
    print(window_size)
    filepath = r''

    # Load and filter trade data
    trades_df = load_trade_data_from_csv(filepath, window_size)
    trades_df = trades_df[(trades_df['symbol'] == symbol) & 
                          (trades_df['entry_dt'] >= start_date) & 
                          (trades_df['entry_dt'] <= end_date)]

    # Generate chart HTML
    chart_html = generate_chart_from_data(trades_df, symbol, window_size)

    # Render HTML page with chart
    return render(request, 'trades/account_trades.html', {
        'chart_html': chart_html,
        'symbol': symbol,
        'start_date': start_date,
        'end_date': end_date,
        'window_size': window_size,
    })
