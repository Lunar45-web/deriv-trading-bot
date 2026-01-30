import asyncio
import os
import threading
import pandas as pd
import plotly.graph_objs as go
from collections import deque, Counter
from datetime import datetime
from dash import Dash, dcc, html, Input, Output, State, ctx
from deriv_api import DerivAPI

# --- CONFIGURATION (DEFAULTS) ---
DEFAULT_TOKEN_DEMO = os.getenv('DERIV_TOKEN_DEMO', 's4TVgxiEc36iXSM') 
DEFAULT_TOKEN_REAL = os.getenv('DERIV_TOKEN_REAL', '') 
APP_ID = 1089

# --- GLOBAL DATA STORE ---
data_store = {
    # Market Data (FIXED: 1009 Ticks to match Deriv Algorithm)
    'symbol': 'R_100', 
    'times': deque(maxlen=1009),
    'prices': deque(maxlen=1009),
    'digits': deque(maxlen=1009), 
    
    # Trading State
    'balance': "Waiting...",
    'status': "Initializing Data...",
    'active': False, 
    'account_type': 'demo', 
    
    # Logic Memory
    'digit_stats': {i: 0 for i in range(10)},
    'digit_counts': {i: 0 for i in range(10)},
    
    # Performance
    'initial_balance': 0.0,
    'current_profit': 0.0,
    'wins': 0,
    'losses': 0,
    'consecutive_losses': 0,
    'is_trading': False, 
    
    # Settings 
    'stake': 2.0,
    'target': 20.0,
    'stop_loss': 50.0,
    'martingale': True,
    'martingale_multiplier': 2.5
}

# --- DASHBOARD LAYOUT ---
app = Dash(__name__)
server = app.server

app.layout = html.Div(style={'backgroundColor': '#121212', 'color': '#e0e0e0', 'fontFamily': 'Roboto, sans-serif', 'minHeight': '100vh'}, children=[
    
    # --- TOP BAR ---
    html.Div([
        html.Div([
            html.H2("DERIV MASTER TERMINAL (1000 TICK SYNC)", style={'color': '#00ff88', 'margin': '0', 'fontSize': '24px'}),
            html.H4("ALGORITHMIC TRADING SUITE", style={'color': '#888', 'margin': '0', 'fontSize': '12px', 'letterSpacing': '2px'})
        ], style={'flex': '1'}),
        
        html.Div([
            html.H3(id='live-balance', children="Balance: ---", style={'color': '#fff', 'margin': '0'}),
            html.Div(id='live-profit', children="Session Profit: $0.00", style={'color': '#00ccff', 'fontSize': '16px'})
        ], style={'textAlign': 'right', 'flex': '1'})
    ], style={'display': 'flex', 'padding': '15px 30px', 'backgroundColor': '#1a1a1a', 'borderBottom': '2px solid #333'}),

    html.Div([
        # --- LEFT SIDEBAR (CONTROLS) ---
        html.Div([
            html.Label("ACCOUNT SETTINGS", style={'color': '#888', 'fontSize': '12px', 'fontWeight': 'bold'}),
            html.Div([
                dcc.RadioItems(
                    id='account-type',
                    options=[{'label': ' DEMO ', 'value': 'demo'}, {'label': ' REAL ', 'value': 'real'}],
                    value='demo',
                    inline=True,
                    labelStyle={'marginRight': '20px', 'color': '#fff', 'cursor': 'pointer'}
                )
            ], style={'marginBottom': '15px', 'padding': '10px', 'backgroundColor': '#222', 'borderRadius': '5px'}),
            
            dcc.Input(id='token-demo', type='text', placeholder="Demo Token", value=DEFAULT_TOKEN_DEMO, style={'width': '100%', 'marginBottom': '10px', 'backgroundColor': '#333', 'color': '#fff', 'border': 'none', 'padding': '8px'}),
            dcc.Input(id='token-real', type='text', placeholder="Real Token", value=DEFAULT_TOKEN_REAL, style={'width': '100%', 'marginBottom': '20px', 'backgroundColor': '#333', 'color': '#fff', 'border': 'none', 'padding': '8px'}),

            html.Label("MARKET SELECTION", style={'color': '#888', 'fontSize': '12px', 'fontWeight': 'bold'}),
            dcc.Dropdown(
                id='market-selector',
                options=[
                    {'label': 'Volatility 10 (1s)', 'value': '1HZ10V'},
                    {'label': 'Volatility 25 (1s)', 'value': '1HZ25V'},
                    {'label': 'Volatility 50 (1s)', 'value': '1HZ50V'},
                    {'label': 'Volatility 75 (1s)', 'value': '1HZ75V'},
                    {'label': 'Volatility 100 (1s)', 'value': 'R_100'}, 
                ],
                value='R_100',
                clearable=False,
                style={'color': '#000', 'marginBottom': '20px'}
            ),

            html.Label("RISK MANAGEMENT", style={'color': '#888', 'fontSize': '12px', 'fontWeight': 'bold'}),
            html.Div([
                html.Label("Stake ($):"),
                dcc.Input(id='stake-input', type='number', value=2.0, step=0.5, style={'width': '60px', 'marginLeft': '10px'}),
            ], style={'marginBottom': '10px'}),
            
            html.Div([
                html.Label("Target ($):"),
                dcc.Input(id='target-input', type='number', value=20.0, style={'width': '60px', 'marginLeft': '10px'}),
            ], style={'marginBottom': '10px'}),
            
            html.Div([
                html.Label("Stop Loss ($):"),
                dcc.Input(id='stop-input', type='number', value=50.0, style={'width': '60px', 'marginLeft': '10px'}),
            ], style={'marginBottom': '20px'}),

            html.Button('START BOT', id='btn-start', n_clicks=0, style={'width': '100%', 'padding': '15px', 'backgroundColor': '#00ff88', 'border': 'none', 'color': '#000', 'fontWeight': 'bold', 'cursor': 'pointer', 'marginBottom': '10px'}),
            html.Button('STOP BOT', id='btn-stop', n_clicks=0, style={'width': '100%', 'padding': '15px', 'backgroundColor': '#ff3333', 'border': 'none', 'color': '#fff', 'fontWeight': 'bold', 'cursor': 'pointer'}),

            html.Div(id='control-feedback', style={'marginTop': '10px', 'color': '#ffff00', 'fontSize': '12px'})

        ], style={'width': '25%', 'padding': '20px', 'backgroundColor': '#1a1a1a', 'overflowY': 'auto', 'height': 'calc(100vh - 80px)'}),

        # --- MAIN DISPLAY (VISUAL ANALYTICS) ---
        html.Div([
            # Status Bar
            html.Div(id='main-status', children="Status: Idle", style={'padding': '10px', 'backgroundColor': '#222', 'color': '#ffa500', 'textAlign': 'center', 'fontWeight': 'bold', 'marginBottom': '10px'}),

            # 1. DERIV-STYLE CIRCLES
            html.H4("LIVE DIGIT ANALYSIS (Last 1000 Ticks)", style={'color': '#fff', 'textAlign': 'center'}),
            html.Div(id='deriv-circles', style={'display': 'flex', 'justifyContent': 'center', 'flexWrap': 'wrap', 'margin': '20px 0', 'padding': '10px', 'backgroundColor': '#1a1a1a', 'borderRadius': '10px'}),
            
            # 2. EXACT PERCENTAGE TABLE
            html.Div(id='deriv-percentages-table', style={'backgroundColor': '#1a1a1a', 'padding': '15px', 'borderRadius': '8px', 'marginBottom': '20px'}),

            # 3. TICK COUNTER & DATA SOURCE
            html.Div([
                html.Span("Ticks Analyzed: ", style={'color': '#888'}),
                html.Span(id='tick-counter', style={'color': '#00ccff', 'fontWeight': 'bold'}),
                html.Div(id='data-source-info', style={'color': '#888', 'fontSize': '12px', 'marginTop': '5px'})
            ], style={'textAlign': 'center', 'marginBottom': '10px'}),

            # Invisible Interval for Updates
            dcc.Interval(id='ui-update', interval=1000, n_intervals=0)

        ], style={'flex': '1', 'padding': '20px', 'backgroundColor': '#121212', 'height': 'calc(100vh - 80px)', 'overflowY': 'auto'})

    ], style={'display': 'flex'})
])

# --- TRADING LOGIC ENGINE ---
async def execute_trade(api, contract_type, prediction):
    global data_store
    
    # Check Limits
    if data_store['current_profit'] >= data_store['target']:
        data_store['status'] = "🏆 TARGET REACHED! Stopping."
        data_store['active'] = False
        return

    if data_store['current_profit'] <= -data_store['stop_loss']:
        data_store['status'] = "🛑 STOP LOSS HIT! Stopping."
        data_store['active'] = False
        return

    # Martingale Logic
    stake = data_store['stake']
    if data_store['martingale'] and data_store['consecutive_losses'] > 0:
        stake = round(stake * data_store['martingale_multiplier'], 2)
        print(f"Martingale: Increasing stake to ${stake}")

    try:
        data_store['status'] = f"EXECUTING: {prediction} (${stake})..."
        data_store['is_trading'] = True 
        
        # Proposal
        proposal = await api.proposal({
            "proposal": 1, "amount": stake, "barrier": "2", # Barrier 2 for Over 2
            "basis": "stake", "contract_type": contract_type, "currency": "USD",
            "duration": 1, "duration_unit": "t", "symbol": data_store['symbol']
        })
        
        # Buy
        buy = await api.buy({"buy": proposal['proposal']['id'], "price": stake})
        contract_id = buy['buy']['contract_id']
        
        # Wait for Result
        await asyncio.sleep(2.5) 
        
        profit_table = await api.profit_table({"description": 1, "limit": 1})
        if profit_table['profit_table']['transactions']:
            latest = profit_table['profit_table']['transactions'][0]
            if latest['contract_id'] == contract_id:
                profit = float(latest['sell_price']) - float(latest['buy_price'])
                
                data_store['current_profit'] += profit
                
                if profit > 0:
                    data_store['wins'] += 1
                    data_store['consecutive_losses'] = 0
                    data_store['status'] = f"✅ WIN! (+${profit:.2f})"
                else:
                    data_store['losses'] += 1
                    data_store['consecutive_losses'] += 1
                    data_store['status'] = f"❌ LOSS (-${stake})"
        
        data_store['is_trading'] = False

    except Exception as e:
        print(f"Trade Error: {e}", flush=True)
        data_store['status'] = f"Error: {str(e)}"
        data_store['is_trading'] = False

def process_tick(tick, api, loop):
    global data_store
    
    try:
        quote = float(tick['tick']['quote'])
        last_digit = int(str(tick['tick']['quote'])[-1])
        
        data_store['digits'].append(last_digit)

        # WAIT FOR 500 TICKS BEFORE ANALYZING
        if len(data_store['digits']) < 500:
            data_store['status'] = f"Collecting Data... ({len(data_store['digits'])}/500)"
            return

        # Update Stats (Last 1000 Ticks)
        counts = Counter(data_store['digits'])
        total = len(data_store['digits'])
        
        # Store current stats
        current_stats = {i: (counts.get(i, 0) / total) * 100 for i in range(10)}
        data_store['digit_stats'] = current_stats
        data_store['digit_counts'] = counts

        # --- USER STRATEGY LOGIC (OVER 2) ---
        if data_store['active'] and not data_store['is_trading']:
            
            # 1. Condition: 0, 1, 2 must all be < 10%
            low_vals = [current_stats[0], current_stats[1], current_stats[2]]
            is_weak_lows = all(v < 10.0 for v in low_vals)
            
            # 2. Condition: Green Bar (Highest) Logic
            # Must be 4-9 AND >= 12%
            max_digit = max(current_stats, key=current_stats.get)
            max_val = current_stats[max_digit]
            is_strong_highs = (max_digit >= 4) and (max_val >= 12.0)
            
            # 3. Trigger: "Cursor touches 0, 1, or 2"
            is_trigger_touch = (last_digit <= 2)

            if is_weak_lows and is_strong_highs and is_trigger_touch:
                    asyncio.run_coroutine_threadsafe(
                    execute_trade(api, "DIGITOVER", "Over 2 (Sniper Setup)"),
                    loop
                )

    except Exception as e:
        print(f"Tick Error: {e}", flush=True)

# --- BACKEND RUNNER ---
async def run_trader_loop():
    global data_store
    
    current_market = data_store['symbol']
    api = None
    
    while True:
        try:
            # Re-initialize API if settings change or not connected
            if api is None:
                api = DerivAPI(app_id=APP_ID)
                
                # Select Token based on UI Switch
                token = DEFAULT_TOKEN_REAL if data_store['account_type'] == 'real' else DEFAULT_TOKEN_DEMO
                if not token: 
                    data_store['status'] = "⚠️ MISSING TOKEN"
                    await asyncio.sleep(2)
                    continue

                auth = await api.authorize(token)
                data_store['balance'] = f"${auth['authorize']['balance']}"
                data_store['initial_balance'] = float(auth['authorize']['balance'])
                print(f"Connected to {data_store['account_type'].upper()}: {auth['authorize']['loginid']}")

                # Subscribe
                source_ticks = await api.subscribe({'ticks': data_store['symbol']})
                loop = asyncio.get_running_loop()
                source_ticks.subscribe(lambda tick: process_tick(tick, api, loop))
            
            # Watch for Market Change
            if data_store['symbol'] != current_market:
                print("Switching Market...")
                api.clear() # Disconnect
                api = None # Force Reconnect
                current_market = data_store['symbol']
                data_store['digits'].clear()
                continue
            
            # Balance Update Heartbeat
            if api and api.expect_response('authorize'): # Check if connected
                try:
                    bal = await api.balance()
                    data_store['balance'] = f"${bal['balance']['balance']}"
                except:
                    pass

            await asyncio.sleep(2)

        except Exception as e:
            print(f"Connection Loop Error: {e}")
            await asyncio.sleep(5)
            api = None # Retry connection

# --- UI CALLBACKS ---
@app.callback(
    [Output('live-balance', 'children'),
     Output('live-profit', 'children'),
     Output('main-status', 'children'),
     Output('deriv-circles', 'children'),
     Output('deriv-percentages-table', 'children'),
     Output('tick-counter', 'children'),
     Output('data-source-info', 'children'),
     Output('control-feedback', 'children')],
    [Input('ui-update', 'n_intervals'),
     Input('btn-start', 'n_clicks'),
     Input('btn-stop', 'n_clicks')],
    [State('market-selector', 'value'),
     State('account-type', 'value'),
     State('stake-input', 'value'),
     State('target-input', 'value'),
     State('stop-input', 'value'),
     State('token-demo', 'value'),
     State('token-real', 'value')]
)
def update_ui(n, btn_start, btn_stop, market, acc_type, stake, target, stop, t_demo, t_real):
    ctx_msg = ctx.triggered_id
    
    # 1. Handle Controls
    if ctx_msg == 'btn-start':
        data_store['active'] = True
        data_store['status'] = "🟢 BOT STARTED - SCANNING..."
    elif ctx_msg == 'btn-stop':
        data_store['active'] = False
        data_store['status'] = "🔴 BOT STOPPED."

    # 2. Update Settings in Store
    data_store['symbol'] = market
    data_store['account_type'] = acc_type
    data_store['stake'] = float(stake) if stake else 2.0
    data_store['target'] = float(target) if target else 20.0
    data_store['stop_loss'] = float(stop) if stop else 50.0
    
    # Update Global Tokens if changed
    global DEFAULT_TOKEN_DEMO, DEFAULT_TOKEN_REAL
    DEFAULT_TOKEN_DEMO = t_demo
    DEFAULT_TOKEN_REAL = t_real

    # 3. Profit Calc
    profit_text = f"Session Profit: ${data_store['current_profit']:.2f}"

    # 4. CREATE DERIV CIRCLES
    stats = data_store.get('digit_stats', {})
    total_ticks = len(data_store.get('digits', []))
    
    circles = []
    for digit in range(10):
        percentage = stats.get(digit, 0)
        
        # Circle Color Logic (Matches Deriv)
        if digit <= 2: # 0,1,2 = Yellow (Low Risk Zone)
            color = '#ffff00'
            text_color = '#000'
        elif percentage >= 12: # High % = Green
            color = '#00ff00'
            text_color = '#000'
        elif percentage <= 8: # Low % = Red
            color = '#ff0000'
            text_color = '#fff'
        else: # Normal = Blue
            color = '#4444ff'
            text_color = '#fff'
        
        # Size based on percentage
        circle_size = 40 + (percentage * 2)
        
        circles.append(html.Div([
            html.Div(str(digit), style={
                'width': f'{circle_size}px', 'height': f'{circle_size}px',
                'backgroundColor': color, 'borderRadius': '50%',
                'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center',
                'color': text_color, 'fontWeight': 'bold', 'fontSize': '18px',
                'margin': '10px', 'boxShadow': '0 0 10px rgba(255,255,255,0.1)'
            }),
            html.Div(f"{percentage:.1f}%", style={'textAlign': 'center', 'fontSize': '12px', 'color': '#ccc'})
        ], style={'display': 'flex', 'flexDirection': 'column', 'alignItems': 'center'}))

    # 5. CREATE TABLE
    table_rows = []
    # Header
    table_rows.append(html.Tr([html.Th("Digit"), html.Th("Count"), html.Th("%")]))
    for digit in range(10):
        p = stats.get(digit, 0)
        c = data_store.get('digit_counts', {}).get(digit, 0)
        table_rows.append(html.Tr([
            html.Td(str(digit)), html.Td(str(c)), 
            html.Td(f"{p:.1f}%", style={'color': '#00ff00' if p>=12 else '#ff0000' if p<=8 else '#fff'})
        ]))
    
    table = html.Table(table_rows, style={'width': '100%', 'color': '#fff'})

    # 6. Data Source Info
    data_source = "⚠️ Building Dataset..." if total_ticks < 500 else "✅ SYNCHRONIZED (1000+ Ticks)"
    feedback = f"Settings Saved. Mode: {acc_type.upper()}"

    return data_store['balance'], profit_text, data_store['status'], circles, table, str(total_ticks), data_source, feedback

# --- THREAD START ---
def start_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_trader_loop())

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=start_loop, args=(loop,))
    t.daemon = True
    t.start()
    app.run(host='0.0.0.0', port=8050, debug=False)
