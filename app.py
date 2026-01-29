import asyncio
import os
import threading
import pandas as pd
import plotly.graph_objs as go
from collections import deque
from datetime import datetime
from dash import Dash, dcc, html
from dash.dependencies import Input, Output
from deriv_api import DerivAPI

# --- CONFIGURATION ---
API_TOKEN = os.getenv('DERIV_API_TOKEN', 's4TVgxiEc36iXSM')
APP_ID = 1089
SYMBOL = 'R_100'

# --- GLOBAL DATA STORE ---
data_store = {
    'times': deque(maxlen=100),
    'prices': deque(maxlen=100),
    'digits': deque(maxlen=20),
    'balance': "Waiting...",
    'status': "Initializing...",
    'trades': [],
    'tick_list': [] # For flat market calculation
}

# --- DASHBOARD SETUP ---
app = Dash(__name__)
server = app.server

app.layout = html.Div(style={'backgroundColor': '#111', 'color': '#fff', 'fontFamily': 'sans-serif', 'padding': '20px'}, children=[
    html.H2("Deriv Live Algo-Trader", style={'textAlign': 'center', 'color': '#00d4ff'}),
    
    html.Div([
        html.H4(id='live-balance', children="Balance: Loading..."),
        html.P(id='live-status', children="Status: Connecting...", style={'color': '#ffa500'}),
        html.Div(id='last-digits', style={'fontSize': '20px', 'letterSpacing': '5px', 'margin': '10px 0'})
    ], style={'textAlign': 'center', 'border': '1px solid #333', 'padding': '10px', 'borderRadius': '5px'}),

    dcc.Graph(id='live-chart', animate=False),
    
    dcc.Interval(id='graph-update', interval=2000, n_intervals=0)
])

# --- TRADING LOGIC ---
async def execute_trade(api, contract_type, barrier, prediction_name, quote, dt_object):
    """
    Executes the trade asynchronously so it doesn't block the tick stream.
    """
    global data_store
    
    try:
        print(f"FIRING TRADE: {prediction_name}", flush=True)
        data_store['status'] = f"SIGNAL: {prediction_name}! Buying..."
        
        # Buy Contract
        await api.buy({
            "buy": 1, "price": 0.35,
            "parameters": {
                "contract_type": contract_type, "symbol": SYMBOL,
                "duration": 1, "duration_unit": "t",
                "barrier": str(barrier), "currency": "USD", "basis": "stake"
            }
        })
        
        # Log Trade
        data_store['trades'].append({'time': dt_object, 'price': quote, 'type': 'UP'})
        data_store['status'] = f"Trade Placed: {prediction_name}"
        
        # Update Balance
        await asyncio.sleep(2)
        bal = await api.balance()
        data_store['balance'] = f"Balance: ${bal['balance']['balance']}"
        
    except Exception as e:
        print(f"Trade Error: {e}", flush=True)
        data_store['status'] = f"Trade Error: {str(e)}"

def process_tick(tick, api, loop):
    """
    This function runs EVERY time a new tick arrives.
    """
    global data_store
    
    try:
        # 1. Parse Data
        quote = float(tick['tick']['quote'])
        epoch = int(tick['tick']['epoch'])
        last_digit = int(str(tick['tick']['quote'])[-1])
        dt_object = datetime.fromtimestamp(epoch)

        # 2. Update Global Store (Instant)
        data_store['times'].append(dt_object)
        data_store['prices'].append(quote)
        data_store['digits'].append(last_digit)
        
        # 3. Strategy Calculation
        tick_list = data_store['tick_list']
        tick_list.append(quote)
        if len(tick_list) > 5:
            tick_list.pop(0)

        # 4. Check Signal (Flat Market Trap)
        if len(tick_list) == 5:
            volatility = max(tick_list) - min(tick_list)
            
            # STRATEGY: Low Volatility (< 0.5) AND Low Digit (<= 2)
            if volatility < 0.5 and last_digit <= 2:
                # We use the loop to fire the async trade from this sync callback
                asyncio.run_coroutine_threadsafe(
                    execute_trade(api, "DIGITOVER", "2", "Over 2", quote, dt_object), 
                    loop
                )

    except Exception as e:
        print(f"Tick Error: {e}", flush=True)

async def run_trader():
    global data_store
    api = DerivAPI(app_id=APP_ID)

    try:
        # Login
        auth = await api.authorize(API_TOKEN)
        data_store['balance'] = f"Demo Balance: ${auth['authorize']['balance']}"
        data_store['status'] = f"Connected: {auth['authorize']['loginid']}"
        print(f"Logged in: {auth['authorize']['loginid']}", flush=True)

        # Subscribe
        source_ticks = await api.subscribe({'ticks': SYMBOL})
        
        # Get the current event loop so we can fire trades from inside the callback
        loop = asyncio.get_running_loop()
        
        # THE FIX: Use .subscribe() instead of async for
        source_ticks.subscribe(lambda tick: process_tick(tick, api, loop))
        
        # Keep the bot alive forever
        while True:
            await asyncio.sleep(1)

    except Exception as e:
        data_store['status'] = f"CRITICAL ERROR: {str(e)}"
        print(f"Error: {e}", flush=True)

# --- CALLBACKS ---
@app.callback(
    [Output('live-chart', 'figure'),
     Output('live-balance', 'children'),
     Output('live-status', 'children'),
     Output('last-digits', 'children')],
    [Input('graph-update', 'n_intervals')]
)
def update_graph_scatter(n):
    # Safe data extraction
    times = list(data_store['times'])
    prices = list(data_store['prices'])
    
    trace_price = go.Scatter(
        x=times, y=prices,
        mode='lines+markers', name='Price',
        line=dict(color='#00d4ff', width=2)
    )
    
    trade_times = [t['time'] for t in data_store['trades']]
    trade_prices = [t['price'] for t in data_store['trades']]
    
    trace_trades = go.Scatter(
        x=trade_times, y=trade_prices,
        mode='markers', name='Entry',
        marker=dict(color='#00ff00', symbol='triangle-up', size=15)
    )

    layout = go.Layout(
        plot_bgcolor='#111', paper_bgcolor='#111',
        font=dict(color='#fff'),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor='#333'),
        margin=dict(l=40, r=20, t=30, b=30)
    )
    
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
    # Start Trading Bot
    new_loop = asyncio.new_event_loop()
    t = threading.Thread(target=start_background_loop, args=(new_loop,))
    t.daemon = True
    t.start()
    
    # Start Dashboard
    app.run(host='0.0.0.0', port=8050, debug=False)
