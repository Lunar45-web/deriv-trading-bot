import asyncio
import os
import threading
import plotly.graph_objs as go
from collections import deque
from datetime import datetime
from dash import Dash, dcc, html, dash_table
from dash.dependencies import Input, Output, State
from deriv_api import DerivAPI

# --- CONFIGURATION ---
API_TOKEN = os.getenv('DERIV_API_TOKEN', 's4TVgxiEc36iXSM')
APP_ID = 1089

# --- GLOBAL DATA STORE ---
data_store = {
    'symbol': 'R_100',  # Default Symbol
    'times': deque(maxlen=50),
    'prices': deque(maxlen=50),
    'digits': deque(maxlen=15),
    'balance': "Waiting...",
    'status': "Initializing...",
    'trades': [], # List of trade results
    'wins': 0,
    'losses': 0,
    'tick_list': [] # For strategy calculation
}

# --- DASHBOARD SETUP ---
app = Dash(__name__)
server = app.server

app.layout = html.Div(style={'backgroundColor': '#0a0a0a', 'color': '#e0e0e0', 'fontFamily': 'monospace', 'padding': '20px'}, children=[
    
    # Header & Balance
    html.Div([
        html.H2("DERIV SNIPER COMMAND", style={'color': '#00ffcc', 'marginBottom': '5px'}),
        html.H3(id='live-balance', children="Balance: Loading...", style={'color': '#fff', 'fontWeight': 'bold'}),
        html.Div(id='live-status', children="Status: Connecting...", style={'color': '#ffa500', 'marginBottom': '10px'}),
    ], style={'textAlign': 'center', 'borderBottom': '1px solid #333', 'paddingBottom': '10px'}),

    # Controls & Stats
    html.Div([
        html.Div([
            html.Label("Target Market:"),
            dcc.Dropdown(
                id='symbol-selector',
                options=[
                    {'label': 'Volatility 100 (1s)', 'value': 'R_100'},
                    {'label': 'Volatility 75 (1s)', 'value': '1HZ75V'},
                    {'label': 'Volatility 10 (1s)', 'value': '1HZ10V'},
                ],
                value='R_100',
                clearable=False,
                style={'color': '#000', 'width': '200px'}
            )
        ], style={'display': 'inline-block', 'marginRight': '20px', 'verticalAlign': 'top'}),
        
        html.Div(id='stats-panel', style={'display': 'inline-block', 'fontSize': '18px'})
    ], style={'padding': '20px', 'textAlign': 'center'}),

    # Live Chart
    dcc.Graph(id='live-chart', animate=False),

    # Last Digits Stream
    html.Div([
        html.H4("Last 15 Digits (Live):"),
        html.Div(id='last-digits', style={'fontSize': '24px', 'letterSpacing': '8px', 'color': '#00ffcc'})
    ], style={'textAlign': 'center', 'marginTop': '20px', 'padding': '10px', 'backgroundColor': '#1a1a1a'}),
    
    # 1-Second Interval for Updates
    dcc.Interval(id='graph-update', interval=1000, n_intervals=0)
])

# --- TRADING ENGINE ---
async def place_trade(api, contract_type, barrier, amount, prediction):
    """
    Fixed Trading Function with Correct Parameters
    """
    global data_store
    
    try:
        print(f"--- EXECUTING: {prediction} ---", flush=True)
        data_store['status'] = f"EXECUTING: {prediction}..."
        
        # 1. Proposal (Get Quote)
        proposal = await api.proposal({
            "proposal": 1,
            "amount": amount,
            "barrier": str(barrier),
            "basis": "stake",
            "contract_type": contract_type,
            "currency": "USD",
            "duration": 1,
            "duration_unit": "t",
            "symbol": data_store['symbol']
        })
        
        proposal_id = proposal['proposal']['id']
        
        # 2. Buy (Execute)
        buy = await api.buy({"buy": proposal_id, "price": amount})
        
        contract_id = buy['buy']['contract_id']
        data_store['status'] = f"Trade Placed! ID: {contract_id}"
        
        # 3. Wait for Result
        # We assume result comes in quickly. For robust logic, we'd use a transaction stream.
        # Here we just sleep briefly then check profit.
        await asyncio.sleep(2.5) 
        
        # Check Profit
        # This is a simplified check. Ideally, subscribe to 'proposal_open_contract'
        profit_table = await api.profit_table({"description": 1, "limit": 1})
        if profit_table['profit_table']['transactions']:
            latest = profit_table['profit_table']['transactions'][0]
            if latest['contract_id'] == contract_id:
                profit = float(latest['sell_price']) - float(latest['buy_price'])
                if profit > 0:
                    data_store['wins'] += 1
                    data_store['status'] = f"✅ WIN! (+${profit})"
                else:
                    data_store['losses'] += 1
                    data_store['status'] = f"❌ LOSS (-${amount})"

    except Exception as e:
        print(f"Trade Failed: {e}", flush=True)
        data_store['status'] = f"Error: {str(e)}"

def process_tick(tick, api, loop):
    global data_store
    
    try:
        quote = float(tick['tick']['quote'])
        epoch = int(tick['tick']['epoch'])
        last_digit = int(str(tick['tick']['quote'])[-1])
        dt_object = datetime.fromtimestamp(epoch)

        # Update Data
        data_store['times'].append(dt_object)
        data_store['prices'].append(quote)
        data_store['digits'].append(last_digit)
        
        # --- STRATEGY ---
        tick_list = data_store['tick_list']
        tick_list.append(quote)
        if len(tick_list) > 5:
            tick_list.pop(0)

        # Flat Market Logic
        if len(tick_list) == 5:
            volatility = max(tick_list) - min(tick_list)
            
            # Condition: Super Flat (<0.3) AND Low Digit (<=1)
            # Tweaked to be more aggressive for testing
            if volatility < 0.3 and last_digit <= 1:
                # Trigger Async Trade safely
                asyncio.run_coroutine_threadsafe(
                    place_trade(api, "DIGITOVER", "2", 0.35, "Over 2"),
                    loop
                )

    except Exception as e:
        print(f"Tick Error: {e}", flush=True)

async def run_trader():
    global data_store
    api = DerivAPI(app_id=APP_ID)

    try:
        auth = await api.authorize(API_TOKEN)
        data_store['balance'] = f"Account: {auth['authorize']['loginid']} | ${auth['authorize']['balance']}"
        data_store['status'] = "Connected & Scanning..."
        print(f"Logged in: {auth['authorize']['loginid']}", flush=True)
        
        # Initial Subscription
        current_symbol = data_store['symbol']
        source_ticks = await api.subscribe({'ticks': current_symbol})
        
        loop = asyncio.get_running_loop()
        source_ticks.subscribe(lambda tick: process_tick(tick, api, loop))

        # Heartbeat Loop (Checks Balance & Symbol Changes)
        while True:
            # 1. Update Balance
            bal = await api.balance()
            data_store['balance'] = f"Account: {auth['authorize']['loginid']} | ${bal['balance']['balance']}"
            
            # 2. Check for Symbol Change (Basic Implementation)
            # If user changed dropdown, we would need to unsubscribe/resubscribe here.
            # For stability, we stick to the initial symbol in this V1 fix.
            
            await asyncio.sleep(5) # Update balance every 5s

    except Exception as e:
        data_store['status'] = f"Connection Error: {e}"
        print(f"Critical: {e}", flush=True)

# --- CALLBACKS ---
@app.callback(
    [Output('live-chart', 'figure'),
     Output('live-balance', 'children'),
     Output('live-status', 'children'),
     Output('last-digits', 'children'),
     Output('stats-panel', 'children')],
    [Input('graph-update', 'n_intervals'),
     Input('symbol-selector', 'value')] # Listener for dropdown
)
def update_dashboard(n, selected_symbol):
    # Note: Switching symbols live requires complex logic. 
    # For now, we just update the UI logic, but the bot trades the initial symbol.
    
    # 1. Chart
    trace = go.Scatter(
        x=list(data_store['times']),
        y=list(data_store['prices']),
        mode='lines+markers',
        line=dict(color='#00ffcc', width=2),
        marker=dict(size=6)
    )
    
    layout = go.Layout(
        plot_bgcolor='#1a1a1a', paper_bgcolor='#0a0a0a',
        font=dict(color='#fff'),
        margin=dict(l=40, r=20, t=30, b=30),
        height=400,
        xaxis=dict(showgrid=False),
        yaxis=dict(gridcolor='#333')
    )

    # 2. Digits
    digits_display = [
        html.Span(str(d), style={'color': '#ff3333' if d>=7 else '#33ff33' if d<=2 else '#fff', 'padding': '0 5px'})
        for d in list(data_store['digits'])
    ]
    
    # 3. Stats
    stats_text = f"Wins: {data_store['wins']} | Losses: {data_store['losses']}"

    return {'data': [trace], 'layout': layout}, \
           data_store['balance'], \
           data_store['status'], \
           digits_display, \
           stats_text

# --- RUNNER ---
def start_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_trader())

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=start_loop, args=(loop,))
    t.daemon = True
    t.start()
    
    app.run(host='0.0.0.0', port=8050, debug=False)
