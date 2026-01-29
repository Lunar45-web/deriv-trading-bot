import asyncio
import os
import threading
import math
import pandas as pd
import plotly.graph_objs as go
from collections import deque, Counter
from datetime import datetime
from dash import Dash, dcc, html
from dash.dependencies import Input, Output
from deriv_api import DerivAPI

# --- CONFIGURATION ---
API_TOKEN = os.getenv('DERIV_API_TOKEN', 's4TVgxiEc36iXSM')
APP_ID = 1089

# --- MONEY MANAGEMENT ---
BASE_STAKE = 2.0        
RECOVERY_MULTIPLIER = 3.0 # 3x for 40% payout recovery
MAX_RECOVERY_ATTEMPTS = 1

# --- MATH CONSTANTS ---
MIN_SAMPLE = 60
COOLDOWN_TICKS = 5
ENTROPY_THRESHOLD = 2.1 

# --- GLOBALS ---
last_trade_tick = 0
tick_counter = 0

data_store = {
    'symbol': 'R_100',
    'times': deque(maxlen=100),
    'prices': deque(maxlen=100),
    'digits': deque(maxlen=100),
    'balance': "Waiting...",
    'status': "Building Mathematical Model...",
    'trades': [], 
    'wins': 0,
    'losses': 0,
    'consecutive_losses': 0,
    'is_trading': False,
    'digit_stats': {i: 0 for i in range(10)}
}

# --- DASHBOARD ---
app = Dash(__name__)
server = app.server

app.layout = html.Div(style={'backgroundColor': '#0b0c10', 'color': '#c5c6c7', 'fontFamily': 'monospace', 'padding': '20px'}, children=[
    
    html.Div([
        html.H2("DERIV ENTROPY MATH-BOT", style={'color': '#66fcf1', 'letterSpacing': '2px'}),
        html.H3(id='live-balance', children="Balance: Loading...", style={'color': '#fff'}),
        html.Div(id='live-status', children="Status: Calibrating...", style={'color': '#45a29e', 'fontSize': '16px'}),
    ], style={'textAlign': 'center', 'borderBottom': '2px solid #1f2833', 'paddingBottom': '15px'}),

    # Live Digit Frequency Chart
    html.Div([
        dcc.Graph(id='freq-chart', config={'displayModeBar': False}, style={'height': '250px'})
    ], style={'margin': '20px 0', 'border': '1px solid #333'}),

    dcc.Graph(id='live-chart', animate=False, style={'height': '300px'}),

    html.Div([
        html.H4("LIVE FEED:"),
        html.Div(id='last-digits', style={'fontSize': '24px', 'letterSpacing': '8px', 'fontWeight': 'bold'})
    ], style={'textAlign': 'center', 'marginTop': '10px', 'backgroundColor': '#000', 'padding': '10px'}),
    
    dcc.Interval(id='graph-update', interval=1000, n_intervals=0)
])

# --- TRADING EXECUTION ---
async def place_trade(api, contract_type, barrier, prediction):
    global data_store
    
    # Smart Recovery (3x)
    current_stake = BASE_STAKE
    if data_store['consecutive_losses'] > 0 and data_store['consecutive_losses'] <= MAX_RECOVERY_ATTEMPTS:
        current_stake = round(BASE_STAKE * RECOVERY_MULTIPLIER, 2)
        print(f"⚠️ RECOVERY BET: ${current_stake}", flush=True)

    try:
        data_store['status'] = f"SIGNAL: {prediction} (${current_stake})..."
        data_store['is_trading'] = True 
        
        proposal = await api.proposal({
            "proposal": 1, "amount": current_stake, "barrier": str(barrier),
            "basis": "stake", "contract_type": contract_type, "currency": "USD",
            "duration": 1, "duration_unit": "t", "symbol": data_store['symbol']
        })
        
        buy = await api.buy({"buy": proposal['proposal']['id'], "price": current_stake})
        contract_id = buy['buy']['contract_id']
        
        await asyncio.sleep(2.5) 
        
        profit_table = await api.profit_table({"description": 1, "limit": 1})
        if profit_table['profit_table']['transactions']:
            latest = profit_table['profit_table']['transactions'][0]
            if latest['contract_id'] == contract_id:
                profit = float(latest['sell_price']) - float(latest['buy_price'])
                if profit > 0:
                    data_store['wins'] += 1
                    data_store['consecutive_losses'] = 0
                    data_store['status'] = f"✅ WIN! (+${profit:.2f})"
                else:
                    data_store['losses'] += 1
                    data_store['consecutive_losses'] += 1
                    data_store['status'] = f"❌ LOSS (-${current_stake})"
        
        data_store['is_trading'] = False

    except Exception as e:
        print(f"Error: {e}", flush=True)
        data_store['is_trading'] = False

# --- MATHEMATICAL LOGIC ---
def digit_entropy(dist):
    # Calculates Shannon Entropy (Measure of Randomness)
    # dist is a dictionary of percentages {0: 10.5, 1: 9.2...}
    probs = [v/100 for v in dist.values() if v > 0]
    return -sum(p * math.log(p, 2) for p in probs)

def process_tick(tick, api, loop):
    global data_store, tick_counter, last_trade_tick

    try:
        tick_counter += 1

        quote = float(tick['tick']['quote'])
        epoch = int(tick['tick']['epoch'])
        last_digit = int(str(tick['tick']['quote'])[-1])
        dt_object = datetime.fromtimestamp(epoch)

        # Update Visuals
        data_store['times'].append(dt_object)
        data_store['prices'].append(quote)
        data_store['digits'].append(last_digit)

        if len(data_store['digits']) < MIN_SAMPLE:
            data_store['status'] = f"Gathering Samples ({len(data_store['digits'])}/{MIN_SAMPLE})..."
            return

        # Calculate Statistics
        counts = Counter(data_store['digits'])
        total = len(data_store['digits'])
        digit_stats = {i: (counts.get(i, 0) / total) * 100 for i in range(10)}
        data_store['digit_stats'] = digit_stats

        # Don't trade if already busy
        if data_store['is_trading']:
            return

        # --- MECHANISM FILTERS (USER LOGIC) ---

        # 1. Entropy (randomness filter)
        ent = digit_entropy(digit_stats)
        if ent > ENTROPY_THRESHOLD:
            data_store['status'] = f"⛔ Market Random (Ent: {round(ent,2)})"
            return

        # 2. Distribution bias
        low_bias = sum(digit_stats[i] for i in range(0, 4))   # 0,1,2,3
        high_bias = sum(digit_stats[i] for i in range(6, 10)) # 6,7,8,9

        # 3. Cooldown
        if tick_counter - last_trade_tick < COOLDOWN_TICKS:
            data_store['status'] = "❄️ Cooldown..."
            return

        # 4. Spike structure (last 2 ticks)
        recent = list(data_store['digits'])[-2:]

        # -------- UNDER 7 LOGIC --------
        # If High Digits are dominating (>45%) AND we hit an 8 or 9
        if high_bias > 45 and recent[-1] >= 8:
            last_trade_tick = tick_counter
            asyncio.run_coroutine_threadsafe(
                place_trade(api, "DIGITUNDER", "7", "Under 7 (High Distortion)"),
                loop
            )
            return

        # -------- OVER 2 LOGIC --------
        # If Low Digits are dominating (>45%) AND we hit a 0 or 1
        if low_bias > 45 and recent[-1] <= 1:
            last_trade_tick = tick_counter
            asyncio.run_coroutine_threadsafe(
                place_trade(api, "DIGITOVER", "2", "Over 2 (Low Distortion)"),
                loop
            )

    except Exception as e:
        print(f"Tick Error: {e}", flush=True)

async def run_trader():
    global data_store
    api = DerivAPI(app_id=APP_ID)
    try:
        auth = await api.authorize(API_TOKEN)
        print(f"Logged in: {auth['authorize']['loginid']}", flush=True)
        
        source_ticks = await api.subscribe({'ticks': data_store['symbol']})
        loop = asyncio.get_running_loop()
        source_ticks.subscribe(lambda tick: process_tick(tick, api, loop))

        while True:
            bal = await api.balance()
            data_store['balance'] = f"Account: {auth['authorize']['loginid']} | ${bal['balance']['balance']}"
            await asyncio.sleep(5) 
    except Exception as e:
        print(f"Critical: {e}", flush=True)

# --- CALLBACKS ---
@app.callback(
    [Output('live-chart', 'figure'),
     Output('freq-chart', 'figure'),
     Output('live-balance', 'children'),
     Output('live-status', 'children'),
     Output('last-digits', 'children')],
    [Input('graph-update', 'n_intervals')]
)
def update_dashboard(n):
    # 1. Price Chart
    trace_price = go.Scatter(
        x=list(data_store['times']), y=list(data_store['prices']),
        mode='lines', line=dict(color='#66fcf1', width=2)
    )
    layout_price = go.Layout(
        plot_bgcolor='#1f2833', paper_bgcolor='#0b0c10',
        font=dict(color='#c5c6c7'), margin=dict(l=40, r=20, t=10, b=30),
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor='#333')
    )

    # 2. Frequency Chart
    stats = data_store['digit_stats']
    if stats:
        max_freq = max(stats.values())
        min_freq = min(stats.values()) if len(stats) > 1 else 0
        colors = []
        for i in range(10):
            val = stats.get(i, 0)
            if val == max_freq: colors.append('#00ff00') 
            elif val == min_freq: colors.append('#ff0000') 
            else: colors.append('#45a29e')
    else:
        colors = ['#333'] * 10

    trace_freq = go.Bar(
        x=[str(i) for i in range(10)],
        y=[stats.get(i, 0) for i in range(10)],
        marker=dict(color=colors)
    )
    layout_freq = go.Layout(
        title="Probability Distribution (Bias)",
        plot_bgcolor='#1f2833', paper_bgcolor='#0b0c10',
        font=dict(color='#c5c6c7'), margin=dict(l=30, r=20, t=30, b=20),
        yaxis=dict(showgrid=True, gridcolor='#333', title="%")
    )

    # 3. Last Digits Stream
    last_15 = list(data_store['digits'])[-15:]
    digits_display = [
        html.Span(str(d), style={
            'color': '#ff0000' if d>=8 else '#66fcf1' if d<=2 else '#fff', 
            'padding': '0 8px'
        }) for d in last_15
    ]

    return {'data': [trace_price], 'layout': layout_price}, \
           {'data': [trace_freq], 'layout': layout_freq}, \
           data_store['balance'], \
           data_store['status'], \
           digits_display

def start_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_trader())

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=start_loop, args=(loop,))
    t.daemon = True
    t.start()
    app.run(host='0.0.0.0', port=8050, debug=False)
