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
RECOVERY_MULTIPLIER = 2.5 # Aggressive recovery for Over 2
MAX_RECOVERY_ATTEMPTS = 1 

# --- DATA STORE ---
data_store = {
    'symbol': 'R_100',
    'times': deque(maxlen=200),
    'prices': deque(maxlen=200), # Larger buffer for Analysis
    'digits': deque(maxlen=20),
    'balance': "Waiting...",
    'status': "Initializing Analytics...",
    'trades': [], 
    'wins': 0,
    'losses': 0,
    'consecutive_losses': 0,
    'is_trading': False,
    # Live Indicator Values (For Display)
    'rsi': 0,
    'macd': 0,
    'ema': 0
}

# --- DASHBOARD ---
app = Dash(__name__)
server = app.server

app.layout = html.Div(style={'backgroundColor': '#0b0c10', 'color': '#c5c6c7', 'fontFamily': 'sans-serif', 'padding': '20px'}, children=[
    
    html.Div([
        html.H2("TITAN QUANTITATIVE TRADER", style={'color': '#66fcf1', 'letterSpacing': '2px'}),
        html.H3(id='live-balance', children="Balance: Loading...", style={'color': '#fff', 'fontWeight': 'bold'}),
        html.Div(id='live-status', children="Status: Calibrating Indicators...", style={'color': '#45a29e', 'fontSize': '18px'}),
    ], style={'textAlign': 'center', 'borderBottom': '2px solid #1f2833', 'paddingBottom': '15px'}),

    # Live Analytics Panel
    html.Div([
        html.Div(id='indicator-panel', style={'fontSize': '16px', 'color': '#ffd700', 'margin': '10px'})
    ], style={'textAlign': 'center', 'backgroundColor': '#1f2833', 'padding': '10px', 'borderRadius': '5px'}),

    dcc.Graph(id='live-chart', animate=False),

    html.Div([
        html.H4("Digit Heatmap:"),
        html.Div(id='last-digits', style={'fontSize': '24px', 'letterSpacing': '5px'})
    ], style={'textAlign': 'center', 'marginTop': '20px'}),
    
    dcc.Interval(id='graph-update', interval=1000, n_intervals=0)
])

# --- EXECUTION ENGINE ---
async def place_trade(api, contract_type, barrier, prediction):
    global data_store
    
    # Smart Staking Logic
    current_stake = BASE_STAKE
    if data_store['consecutive_losses'] > 0 and data_store['consecutive_losses'] <= MAX_RECOVERY_ATTEMPTS:
        current_stake = BASE_STAKE * RECOVERY_MULTIPLIER
        print(f"⚠️ RECOVERY STAKE: ${current_stake}", flush=True)

    try:
        data_store['status'] = f"SNIPING: {prediction} (${current_stake})..."
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
        print(f"Execution Error: {e}", flush=True)
        data_store['is_trading'] = False

# --- ANALYTICS BRAIN ---
def analyze_market(api, loop):
    global data_store
    
    # Need at least 50 ticks to calculate EMA/RSI accurately
    if len(data_store['prices']) < 50:
        return

    # Convert Deque to Pandas Series for math
    price_series = pd.Series(list(data_store['prices']))
    
    # 1. CALCULATE INDICATORS
    # RSI (Relative Strength Index) - Period 14
    rsi = ta.rsi(price_series, length=14)
    current_rsi = rsi.iloc[-1] if rsi is not None else 50
    
    # EMA (Exponential Moving Average) - Period 50 (Trend)
    ema = ta.ema(price_series, length=50)
    current_ema = ema.iloc[-1] if ema is not None else 0
    current_price = price_series.iloc[-1]
    
    # MACD (Momentum) - Fast 12, Slow 26
    macd = ta.macd(price_series)
    # pandas_ta returns columns: MACD_12_26_9, MACDh_12_26_9 (Hist), MACDs_12_26_9 (Signal)
    macd_line = macd['MACD_12_26_9'].iloc[-1] if macd is not None else 0
    signal_line = macd['MACDs_12_26_9'].iloc[-1] if macd is not None else 0

    # Store for Dashboard
    data_store['rsi'] = round(current_rsi, 2)
    data_store['macd'] = round(macd_line, 5)
    data_store['ema'] = round(current_ema, 2)
    
    # 2. THE TITAN STRATEGY LOGIC
    # Condition A: UPTREND (Price > EMA 50)
    is_uptrend = current_price > current_ema
    
    # Condition B: MOMENTUM (RSI > 50 but not overbought > 75)
    is_momentum = 50 < current_rsi < 75
    
    # Condition C: TRIGGER (MACD > Signal)
    is_trigger = macd_line > signal_line

    # EXECUTE
    if is_uptrend and is_momentum and is_trigger:
        data_store['status'] = "⭐⭐⭐ PERFECT SETUP DETECTED ⭐⭐⭐"
        asyncio.run_coroutine_threadsafe(
            place_trade(api, "DIGITOVER", "2", "Titan Over 2"),
            loop
        )
    else:
        # Feedback for user on why it's waiting
        if not is_uptrend:
            data_store['status'] = "Waiting: Downtrend (Price < EMA)"
        elif not is_momentum:
            data_store['status'] = f"Waiting: Weak Momentum (RSI {round(current_rsi,1)})"
        elif not is_trigger:
            data_store['status'] = "Waiting: MACD Cross"

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
        
        if not data_store['is_trading']:
            analyze_market(api, loop)

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
     Output('indicator-panel', 'children')],
    [Input('graph-update', 'n_intervals')]
)
def update_dashboard(n):
    # Candlestick-style chart
    trace = go.Scatter(
        x=list(data_store['times']), y=list(data_store['prices']),
        mode='lines', line=dict(color='#66fcf1', width=2), fill='tozeroy', fillcolor='rgba(102, 252, 241, 0.1)'
    )
    layout = go.Layout(
        plot_bgcolor='#1f2833', paper_bgcolor='#0b0c10',
        font=dict(color='#c5c6c7'), margin=dict(l=40, r=20, t=30, b=30), height=400,
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor='#333')
    )
    
    digits_display = [
        html.Span(str(d), style={'color': '#66fcf1' if d>=3 else '#ff3333', 'padding': '0 6px', 'fontWeight': 'bold'})
        for d in list(data_store['digits'])
    ]
    
    # Indicator Stats
    stats = f"RSI: {data_store['rsi']} | MACD: {data_store['macd']} | EMA: {data_store['ema']} | Wins: {data_store['wins']} / Losses: {data_store['losses']}"

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
