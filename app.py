import asyncio
import os
import threading
import pandas as pd
import pandas_ta as ta
import plotly.graph_objs as go
from collections import deque
from datetime import datetime
from dash import Dash, dcc, html
from dash.dependencies import Input, Output
from deriv_api import DerivAPI

# --- CONFIGURATION ---
API_TOKEN = os.getenv('DERIV_API_TOKEN', 's4TVgxiEc36iXSM')
APP_ID = 1089
SYMBOL = 'R_100'  # Volatility 100 (1s)
TIMEFRAME = 60    # 1 Minute Candles for MACD analysis

# --- GLOBAL DATA STORE ---
# We use deques (efficient lists) to store live data for the dashboard
data_store = {
    'times': deque(maxlen=100),
    'prices': deque(maxlen=100),
    'digits': deque(maxlen=20),
    'balance': "Waiting...",
    'status': "Initializing...",
    'trades': []  # Stores trade markers: {'time': t, 'price': p, 'type': 'CALL/PUT'}
}

# --- DASHBOARD SETUP ---
app = Dash(__name__)
server = app.server  # For Render to hook into

app.layout = html.Div(style={'backgroundColor': '#111', 'color': '#fff', 'fontFamily': 'sans-serif', 'padding': '20px'}, children=[
    html.H2("Deriv Live Algo-Trader", style={'textAlign': 'center', 'color': '#00d4ff'}),
    
    html.Div([
        html.H4(id='live-balance', children="Balance: Loading..."),
        html.P(id='live-status', children="Status: Connecting...", style={'color': '#ffa500'}),
        html.Div(id='last-digits', style={'fontSize': '20px', 'letterSpacing': '5px', 'margin': '10px 0'})
    ], style={'textAlign': 'center', 'border': '1px solid #333', 'padding': '10px', 'borderRadius': '5px'}),

    dcc.Graph(id='live-chart', animate=False),
    
    # Update the chart every 2 seconds
    dcc.Interval(id='graph-update', interval=2000, n_intervals=0)
])

# --- TRADING LOGIC & DATA STREAM ---
async def run_trader():
    global data_store
    api = DerivAPI(app_id=APP_ID)

    try:
        # 1. Authorize
        auth = await api.authorize(API_TOKEN)
        data_store['balance'] = f"Demo Balance: ${auth['authorize']['balance']}"
        data_store['status'] = f"Connected to: {auth['authorize']['loginid']}"
        print(f"Logged in: {auth['authorize']['loginid']}")

        # 2. Subscribe to Ticks (for digits) AND Candles (for MACD)
        # Note: For simplicity in this 'Lite' version, we build candles from ticks manually 
        # or just use ticks for the chart to ensure speed.
        source_ticks = await api.subscribe({'ticks': SYMBOL})
        
        # 3. Main Loop
        tick_list = [] # Temporary list to build our analysis
        
        async for tick in source_ticks:
            quote = float(tick['tick']['quote'])
            epoch = int(tick['tick']['epoch'])
            last_digit = int(str(tick['tick']['quote'])[-1])
            
            # Update Dashboard Data
            dt_object = datetime.fromtimestamp(epoch)
            data_store['times'].append(dt_object)
            data_store['prices'].append(quote)
            data_store['digits'].append(last_digit)
            
            # --- STRATEGY: "The Flat Market Trap" ---
            # We look for low volatility (flat line) then snipe
            tick_list.append(quote)
            if len(tick_list) > 5:
                tick_list.pop(0)
            
            # Calculate simple volatility (High - Low of last 5 ticks)
            if len(tick_list) == 5:
                volatility = max(tick_list) - min(tick_list)
                
                # If market is VERY flat (diff < 0.5) AND last digit is small
                if volatility < 0.5 and last_digit <= 2:
                    data_store['status'] = "SIGNAL: Flat Market! Buying Over 2..."
                    
                    # PLACING THE TRADE
                    try:
                        # Trade: Over 2
                        await api.buy({
                            "buy": 1, "price": 0.35,
                            "parameters": {
                                "contract_type": "DIGITOVER", "symbol": SYMBOL,
                                "duration": 1, "duration_unit": "t",
                                "barrier": "2", "currency": "USD", "basis": "stake"
                            }
                        })
                        # Log the trade for the chart
                        data_store['trades'].append({'time': dt_object, 'price': quote, 'type': 'UP'})
                        data_store['status'] = "Trade Placed: Over 2"
                        
                        # Update balance after a brief pause
                        await asyncio.sleep(2)
                        bal = await api.balance()
                        data_store['balance'] = f"Balance: ${bal['balance']['balance']}"
                        
                    except Exception as e:
                        data_store['status'] = f"Error: {str(e)}"

    except Exception as e:
        data_store['status'] = f"CRITICAL ERROR: {str(e)}"
        print(f"Error: {e}")

# --- DASHBOARD CALLBACKS (The Visuals) ---
@app.callback(
    [Output('live-chart', 'figure'),
     Output('live-balance', 'children'),
     Output('live-status', 'children'),
     Output('last-digits', 'children')],
    [Input('graph-update', 'n_intervals')]
)
def update_graph_scatter(n):
    # 1. Create the Price Line
    trace_price = go.Scatter(
        x=list(data_store['times']),
        y=list(data_store['prices']),
        mode='lines+markers',
        name='Price',
        line=dict(color='#00d4ff', width=2)
    )
    
    # 2. Add Trade Markers (Green Triangles for Buys)
    trade_times = [t['time'] for t in data_store['trades']]
    trade_prices = [t['price'] for t in data_store['trades']]
    
    trace_trades = go.Scatter(
        x=trade_times,
        y=trade_prices,
        mode='markers',
        name='Trade Entry',
        marker=dict(color='#00ff00', symbol='triangle-up', size=15)
    )

    layout = go.Layout(
        plot_bgcolor='#111',
        paper_bgcolor='#111',
        font=dict(color='#fff'),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor='#333'),
        margin=dict(l=40, r=20, t=30, b=30)
    )
    
    # Format Digits String
    digits_str = " ".join([str(d) for d in list(data_store['digits'])])
    
    return {'data': [trace_price, trace_trades], 'layout': layout}, \
           data_store['balance'], \
           data_store['status'], \
           f"Digits: {digits_str}"

# --- RUNNER ---
def start_background_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_trader())

if __name__ == '__main__':
    # Start the Trading Bot in a Background Thread
    new_loop = asyncio.new_event_loop()
    t = threading.Thread(target=start_background_loop, args=(new_loop,))
    t.daemon = True
    t.start()
    
    # Start the Dashboard (Blocking)
    app.run_server(host='0.0.0.0', port=8050, debug=False)
