import requests
import pandas as pd
from datetime import datetime
from django.shortcuts import render
from django.utils import timezone
from .models import account
import plotly.graph_objects as go
import pytz
from django.http import JsonResponse


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


# Function to fetch trades for a symbol, from a specific account model
def fetch_trades_for_symbol(symbol, start_date, end_date, account_model):
    # Ensure start_date and end_date are strings in correct format
    if isinstance(start_date, str):
        start_date = timezone.make_aware(datetime.strptime(start_date, '%Y-%m-%d'))
    if isinstance(end_date, str):
        end_date = timezone.make_aware(datetime.strptime(end_date, '%Y-%m-%d'))

    # Query the relevant model dynamically using account_model
    trades = account_model.objects.filter(symbol=symbol, time__range=[start_date, end_date]).values(
        'time', 'side', 'price', 'realizedPnl'
    )
    return trades


def generate_chart(symbol, start_date, end_date, account_model):
    # Fetch trades data from MySQL for the given symbol and date range
    trades = fetch_trades_for_symbol(symbol, start_date, end_date, account_model)

    # Skip chart generation if no trades are found
    if not trades:
        return None
    
    # Fetch candlestick data from Binance for the given symbol and date range
    binance_candles = fetch_binance_candlestick_data(symbol, start_time=start_date, end_time=end_date)

    if not binance_candles:
        return "No candlestick data available."

    # Prepare the data for plotting the candlesticks
    chart_data = {
        'x': [candle['Time'] for candle in binance_candles],  # Use 'Time' instead of 'date'
        'open': [candle['Open'] for candle in binance_candles],
        'high': [candle['High'] for candle in binance_candles],
        'low': [candle['Low'] for candle in binance_candles],
        'close': [candle['Close'] for candle in binance_candles],
        'volume': [candle['Volume'] for candle in binance_candles],
    }

    # Create a list to store the arrows (indicating trades) on the chart
    arrows = []

    # Iterate over trades directly as the QuerySet
    for trade in trades:
        trade_time = trade['time']  # Access time from dictionary
        realized_pnl = trade['realizedPnl']
        side = trade['side']
        trade_price = trade['price']
        
        if realized_pnl == 0:  # Opening position
            arrow_type = 'open'
        else:  # Closing position
            arrow_type = 'close'

        # Make both trade_time and chart_data['x'] timezone-naive (or aware, depending on your preference)
        if trade_time.tzinfo:  # If trade_time is timezone-aware
            trade_time = trade_time.astimezone(pytz.utc).replace(tzinfo=None)  # Convert to naive

        # Find the closest candle time (ensure it's timezone-naive too)
        closest_candle_time = min(chart_data['x'], key=lambda x: abs(x - trade_time))

        # Get the corresponding candle data for the closest time
        candle_index = chart_data['x'].index(closest_candle_time)
        open_price = chart_data['open'][candle_index]
        close_price = chart_data['close'][candle_index]
        high_price = chart_data['high'][candle_index]
        low_price = chart_data['low'][candle_index]

        # Place the arrow within the range of the candlestick
        # You can adjust this offset to ensure the arrow stays inside the candlestick body
        arrow_y = close_price if side == 'BUY' else open_price

        # Adjust the arrow's position slightly within the body of the candlestick
        offset = 0.2  # You can tweak this value to position the arrow more accurately
        if arrow_type == 'open':
            arrow_y += offset  # Place the arrow slightly above the open price
        elif arrow_type == 'close':
            arrow_y -= offset  # Place the arrow slightly below the close price

        # Add the arrow to the chart
        arrow_color = 'green' if side == 'BUY' else 'red'
        arrows.append(
            dict(
                x=[closest_candle_time],  # Place arrow at the corresponding time
                y=[arrow_y],  # Place the arrow within the candlestick body
                mode='markers',
                marker=dict(symbol='arrow-bar-up' if arrow_type == 'open' else 'arrow-bar-down', 
                            color=arrow_color, size=12),
                name=f'{side} position',
                text=f'Price: {trade_price} | Side: {side} | Time: {trade_time} | RealizedPnl: {realized_pnl}',
                hoverinfo='text',
            )
        )

    # Create the candlestick chart
    fig = go.Figure(data=[go.Candlestick(
        x=chart_data['x'],
        open=chart_data['open'],
        high=chart_data['high'],
        low=chart_data['low'],
        close=chart_data['close'],
        name="Binance Candles"
    )])

    # Add arrows to the chart (trades)
    for arrow in arrows:
        fig.add_trace(go.Scatter(
            x=arrow['x'],
            y=arrow['y'],
            mode=arrow['mode'],
            marker=arrow['marker'],
            name=arrow['name'],
            text=arrow['text'],
            hoverinfo=arrow['hoverinfo']
        ))

    # Update chart layout
    fig.update_layout(
        title=f'{symbol} Trading Chart',
        xaxis_title='Time',
        yaxis_title='Price',
    )

    chart_html = fig.to_html(full_html=False)  # Generate the chart HTML

    return chart_html





# View to render the account trades page
def account_trades_view(request):
    # Get symbol and date range from GET request, or default to BTCUSDT and the current month
    symbol = request.GET.get('symbol', 'BTCUSDT')
    start_date = request.GET.get('start_date', datetime.now().replace(day=1).strftime('%Y-%m-%d'))
    end_date = request.GET.get('end_date', datetime.now().strftime('%Y-%m-%d'))

    # List of account models
    account_models = [
        account
    ]
    
    # Create a dictionary to store the charts
    charts_html = {}
    is_loading = True  # Set flag to indicate loading is in progress

    # Generate charts for all accounts
    for account_model in account_models:
        chart_html = generate_chart(symbol, start_date, end_date, account_model)
        if chart_html:
            charts_html[account_model.__name__] = chart_html

    # Once all charts are ready, set the loading flag to False
    is_loading = False

    # Return the rendered page with all the charts
    return render(request, 'trades/account_trades.html', {
        'charts_html': charts_html,
        'symbol': symbol,
        'start_date': start_date,
        'end_date': end_date,
        'is_loading': is_loading,  # Send the loading flag
    })