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

# --- SMART MONEY MANAGEMENT ---
BASE_STAKE = 2.0        
RECOVERY_MULTIPLIER = 3.0 # Set to 3x to conquer the 40% payout
MAX_RECOVERY_ATTEMPTS = 1 # Safety cap

# --- DATA STORE ---
data_store = {
    'symbol': 'R_100',
    'times': deque(maxlen=100),
    'prices': deque(maxlen=100),
    'digits': deque(maxlen=20),
    'balance': "Waiting...",
    'status': "Initializing Digit Logic...",
    'trades': [], 
    'wins': 0,
    'losses': 0,
    'consecutive_losses': 0,
    'is_trading': False,
    'rsi': 50 # Default neutral
}

# --- DASHBOARD ---
app = Dash(__name__)
server = app.server

app.layout = html.Div(style={'backgroundColor': '#000000', 'color': '#00ff00', 'fontFamily': 'Courier New', 'padding': '20px'}, children=[
    
    html.Div([
        html.H2("DERIV DIGIT DOMINATOR", style={'color': '#00ff00', 'fontWeight': 'bold'}),
        html.H3(id='live-balance', children="Balance: Loading...", style={'color': '#fff'}),
        html.Div(id='live-status', children="Status: Scanning Digits...", style={'color': '#ffff00', 'fontSize': '18px'}),
    ], style={'textAlign': 'center', 'borderBottom': '1px solid #333', 'paddingBottom': '15px'}),

    # RSI Safety Gauge
    html.Div(id='rsi-panel', style={'textAlign': 'center', 'color': '#00ffff', 'margin': '10px'}),

    dcc.Graph(id='live-chart', animate=False),

    html.Div([
        html.H4("LIVE DIGIT STREAM:"),
        html.Div(id='last-digits', style={'fontSize': '28px', 'letterSpacing': '8px', 'fontWeight': 'bold'})
    ], style={'textAlign': 'center', 'marginTop': '20px', 'backgroundColor': '#111', 'padding': '15px'}),
    
    dcc.Interval(id='graph-update', interval=1000, n_intervals=0)
])

# --- TRADING EXECUTION ---
async def place_trade(api, contract_type, barrier, prediction):
    global data_store
    
    # 1. Money Management (The 3x Fix)
    current_stake = BASE_STAKE
    if data_store['consecutive_losses'] > 0 and data_store['consecutive_losses'] <= MAX_RECOVERY_ATTEMPTS:
        current_stake = round(BASE_STAKE * RECOVERY_MULTIPLIER, 2)
        print(f"⚠️ RECOVERY MODE: ${current_stake}", flush=True)

    try:
        data_store['status'] = f"FIRING: {prediction} (${current_stake})..."
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

# --- THE LOGIC: DIGITS + RSI FILTER ---
def process_tick(tick, api, loop):
    global data_store
    
    try:
        quote = float(tick['tick']['quote'])
        epoch = int(tick['tick']['epoch'])
        last_digit = int(str(tick['tick']['quote'])[-1])
        dt_object = datetime.fromtimestamp(epoch)

        data_store['times'].append(dt_object)
        data_store['prices'].append(quote)
        data_store['digits'].append(last_digit)
        
        if data_store['is_trading']:
            return

        # 1. Update RSI (The Safety Filter)
        if len(data_store['prices']) > 20:
            price_series = pd.Series(list(data_store['prices']))
            rsi = ta.rsi(price_series, length=14)
            data_store['rsi'] = round(rsi.iloc[-1], 1) if rsi is not None else 50
        
        current_rsi = data_store['rsi']

        # 2. STRATEGY A: UNDER 7 (Reversal)
        # Logic: High Digit (8/9) -> Bet Low.
        # Filter: DON'T bet if RSI > 75 (Market is skyrocketing)
        if last_digit >= 8:
            if current_rsi < 75:
                asyncio.run_coroutine_threadsafe(
                    place_trade(api, "DIGITUNDER", "7", "Under 7 (Digit Reversion)"),
                    loop
                )
            else:
                data_store['status'] = f"⚠️ Skipped Under 7: RSI Too High ({current_rsi})"
            return

        # 3. STRATEGY B: OVER 2 (Flat/Safe)
        # Logic: Low Digit (0/1/2) + Flat Market -> Bet High.
        # Filter: DON'T bet if RSI < 25 (Market is crashing)
        tick_list = list(data_store['prices'])[-5:]
        if len(tick_list) == 5:
            volatility = max(tick_list) - min(tick_list)
            if volatility < 0.4 and last_digit <= 2:
                if current_rsi > 25:
                    asyncio.run_coroutine_threadsafe(
                        place_trade(api, "DIGITOVER", "2", "Over 2 (Safe Zone)"),
                        loop
                    )
                else:
                    data_store['status'] = f"⚠️ Skipped Over 2: RSI Too Low ({current_rsi})"

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
     Output('live-balance', 'children'),
     Output('live-status', 'children'),
     Output('last-digits', 'children'),
     Output('rsi-panel', 'children')],
    [Input('graph-update', 'n_intervals')]
)
def update_dashboard(n):
    trace = go.Scatter(
        x=list(data_store['times']), y=list(data_store['prices']),
        mode='lines+markers', line=dict(color='#00ff00', width=2), marker=dict(size=5)
    )
    layout = go.Layout(
        plot_bgcolor='#111', paper_bgcolor='#000',
        font=dict(color='#00ff00'), margin=dict(l=40, r=20, t=30, b=30), height=350,
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor='#333')
    )
    
    digits_display = [
        html.Span(str(d), style={'color': '#ff0000' if d>=8 else '#00ff00' if d<=2 else '#888', 'padding': '0 8px', 'fontWeight': 'bold'})
        for d in list(data_store['digits'])
    ]
    
    stats = f"Current RSI: {data_store['rsi']} | Wins: {data_store['wins']} / Losses: {data_store['losses']}"

    return {'data': [trace], 'layout': layout}, data_store['balance'], data_store['status'], digits_display, stats

def start_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_trader())

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=start_loop, args=(loop,))
    t.daemon = True
    t.start()
    app.run(host='0.0.0.0', port=8050, debug=False)
