import asyncio
import os
import threading
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
RECOVERY_MULTIPLIER = 3.0 # 3x covers the 40% payout loss
MAX_RECOVERY_ATTEMPTS = 1

# --- DATA STORE ---
data_store = {
    'symbol': 'R_100',
    'times': deque(maxlen=100),
    'prices': deque(maxlen=100),
    'digits': deque(maxlen=100), # Expanded to 100 for Statistics
    'balance': "Waiting...",
    'status': "Analyzing Digit Frequencies...",
    'trades': [], 
    'wins': 0,
    'losses': 0,
    'consecutive_losses': 0,
    'is_trading': False,
    'digit_stats': {i: 0 for i in range(10)} # Stores count of 0-9
}

# --- DASHBOARD ---
app = Dash(__name__)
server = app.server

app.layout = html.Div(style={'backgroundColor': '#111', 'color': '#fff', 'fontFamily': 'sans-serif', 'padding': '20px'}, children=[
    
    html.Div([
        html.H2("DERIV FREQUENCY MASTER", style={'color': '#00ff00', 'fontWeight': 'bold'}),
        html.H3(id='live-balance', children="Balance: Loading...", style={'color': '#fff'}),
        html.Div(id='live-status', children="Status: Building Statistics...", style={'color': '#ffff00', 'fontSize': '16px'}),
    ], style={'textAlign': 'center', 'borderBottom': '1px solid #333', 'paddingBottom': '15px'}),

    # Live Digit Frequency Chart
    html.Div([
        dcc.Graph(id='freq-chart', config={'displayModeBar': False}, style={'height': '250px'})
    ], style={'margin': '20px 0', 'border': '1px solid #333'}),

    # Price Chart
    dcc.Graph(id='live-chart', animate=False, style={'height': '300px'}),

    # Last 15 Digits Stream
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
        print(f"Error: {e}", flush=True)
        data_store['is_trading'] = False

# --- THE LOGIC: DIGIT FREQUENCY ANALYSIS ---
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
        
        # Update Frequency Stats (Last 100 ticks)
        if len(data_store['digits']) > 0:
            counts = Counter(list(data_store['digits']))
            # Normalize to percentages (roughly, since we keep ~100 digits)
            total = len(data_store['digits'])
            data_store['digit_stats'] = {k: (v/total)*100 for k, v in counts.items()}
            
            # Identify HOT (Green) and COLD (Red) digits
            most_common = counts.most_common(1)[0][0]  # The "Green" Digit
            
            # --- STRATEGY LOGIC ---
            if not data_store['is_trading'] and total >= 25: # Wait for data
                
                # STRATEGY 1: OVER 2 (Bias High)
                # Condition: The Most Frequent Digit is High (4,5,6,7,8,9)
                # Trigger: Current digit dips to 0, 1, or 2
                if most_common >= 4: 
                    if last_digit <= 2:
                        asyncio.run_coroutine_threadsafe(
                            place_trade(api, "DIGITOVER", "2", "Over 2 (High Bias)"),
                            loop
                        )
                        return

                # STRATEGY 2: UNDER 7 (Bias Low)
                # Condition: The Most Frequent Digit is Low (0,1,2,3,4,5)
                # Trigger: Current digit spikes to 8 or 9
                if most_common <= 5:
                    if last_digit >= 8:
                        asyncio.run_coroutine_threadsafe(
                            place_trade(api, "DIGITUNDER", "7", "Under 7 (Low Bias)"),
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
        mode='lines', line=dict(color='#00ff00', width=2)
    )
    layout_price = go.Layout(
        plot_bgcolor='#111', paper_bgcolor='#000',
        font=dict(color='#fff'), margin=dict(l=40, r=20, t=10, b=30),
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor='#333')
    )

    # 2. Frequency Chart (The "Green/Red" Analysis)
    stats = data_store['digit_stats']
    # Color logic: Green for highest, Red for lowest, Blue for others
    if stats:
        max_freq = max(stats.values())
        min_freq = min(stats.values()) if len(stats) > 1 else 0
        colors = []
        for i in range(10):
            val = stats.get(i, 0)
            if val == max_freq: colors.append('#00ff00') # Green
            elif val == min_freq: colors.append('#ff0000') # Red
            else: colors.append('#00ccff') # Blue
    else:
        colors = ['#333'] * 10

    trace_freq = go.Bar(
        x=[str(i) for i in range(10)],
        y=[stats.get(i, 0) for i in range(10)],
        marker=dict(color=colors)
    )
    layout_freq = go.Layout(
        title="Live Digit Frequency (%)",
        plot_bgcolor='#111', paper_bgcolor='#000',
        font=dict(color='#fff'), margin=dict(l=30, r=20, t=30, b=20),
        yaxis=dict(showgrid=True, gridcolor='#333', title="%")
    )

    # 3. Last Digits Stream
    last_15 = list(data_store['digits'])[-15:]
    digits_display = [
        html.Span(str(d), style={
            'color': '#ff0000' if d>=8 else '#00ff00' if d<=2 else '#fff', 
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
