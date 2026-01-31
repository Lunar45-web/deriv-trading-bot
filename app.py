import asyncio
import os
import threading
import pandas as pd
import plotly.graph_objs as go
from collections import deque, Counter
from datetime import datetime
from dash import Dash, dcc, html, Input, Output, State, ctx, no_update
from deriv_api import DerivAPI

# --- CONFIGURATION ---
DEFAULT_TOKEN_DEMO = os.getenv('DERIV_TOKEN_DEMO', 's4TVgxiEc36iXSM') 
DEFAULT_TOKEN_REAL = os.getenv('DERIV_TOKEN_REAL', '') 
APP_ID = 1089

# --- GLOBAL DATA ---
data_store = {
    'symbol': 'R_100', 
    'times': deque(maxlen=1000),
    'prices': deque(maxlen=1000),
    'digits': deque(maxlen=1000), 
    
    'balance': "Loading...",
    'status': "Connecting...",
    'account_type': 'demo',
    
    # Analysis
    'digit_stats': {i: 0 for i in range(10)},
    'prev_stats': {i: 0 for i in range(10)},
    'ranks': {},
    'is_ready': False, # Data Lock
    
    # Trade State
    'last_trade_result': None,
    'current_profit': 0.0,
}

# --- STYLES (DERIV REPLICA) ---
STYLE_BG = '#ffffff'
STYLE_TEXT = '#333333'
STYLE_SIDEBAR = '#f2f3f5'
STYLE_GREEN = '#008832' # Deriv Green
STYLE_RED = '#cc0000'   # Deriv Red

app = Dash(__name__)
server = app.server

app.layout = html.Div(style={'backgroundColor': STYLE_BG, 'color': STYLE_TEXT, 'fontFamily': 'Roboto, sans-serif', 'height': '100vh', 'display': 'flex', 'flexDirection': 'column'}, children=[
    
    # --- 1. HEADER (Top Bar) ---
    html.Div([
        html.Img(src='https://deriv.com/img/deriv-logo.svg', style={'height': '25px', 'marginRight': '20px'}),
        html.Div("Smart Trader Hub", style={'fontWeight': 'bold', 'fontSize': '16px'}),
        html.Div([
            html.Span(id='live-balance', children="---", style={'fontWeight': 'bold', 'marginRight': '20px'}),
            dcc.Dropdown(id='account-type', options=[{'label': 'Demo Account', 'value': 'demo'}, {'label': 'Real Account', 'value': 'real'}], value='demo', clearable=False, style={'width': '150px', 'display': 'inline-block'})
        ], style={'marginLeft': 'auto', 'display': 'flex', 'alignItems': 'center'})
    ], style={'padding': '10px 20px', 'borderBottom': '1px solid #e6e6e6', 'display': 'flex', 'alignItems': 'center', 'backgroundColor': '#fff'}),

    # --- 2. MAIN CONTENT (Split View) ---
    html.Div([
        
        # LEFT: CHART & STATS
        html.Div([
            # Market Selector
            html.Div([
                dcc.Dropdown(id='market-selector', options=[
                    {'label': 'Volatility 10 Index', 'value': '1HZ10V'},
                    {'label': 'Volatility 100 Index', 'value': 'R_100'}
                ], value='R_100', clearable=False, style={'width': '250px', 'marginBottom': '10px'})
            ], style={'position': 'absolute', 'top': '10px', 'left': '20px', 'zIndex': '100'}),

            # Main Chart
            dcc.Graph(id='main-chart', config={'displayModeBar': False}, style={'height': '60vh'}),

            # BOTTOM: DERIV CIRCLES (The "Worm")
            html.Div([
                html.Div("Last Digit Stats (1000 Ticks)", style={'fontSize': '12px', 'color': '#999', 'marginBottom': '5px', 'textAlign': 'center'}),
                html.Div(id='deriv-circles', style={'display': 'flex', 'justifyContent': 'center', 'padding': '10px'})
            ], style={'height': '20vh', 'borderTop': '1px solid #e6e6e6', 'backgroundColor': '#fff'})

        ], style={'flex': '3', 'position': 'relative', 'borderRight': '1px solid #e6e6e6'}),

        # RIGHT: TRADE PANEL (Controls)
        html.Div([
            html.H4("Over/Under", style={'marginTop': '0'}),
            
            # Logic Status Panel
            html.Div(id='logic-status-box', style={'padding': '15px', 'backgroundColor': '#e6f7ff', 'borderRadius': '5px', 'marginBottom': '20px', 'border': '1px solid #1890ff', 'fontSize': '13px'}),

            # Inputs
            html.Label("Stake", style={'fontWeight': 'bold', 'fontSize': '12px'}),
            dcc.Input(id='stake-input', type='number', value=10.0, style={'width': '100%', 'padding': '10px', 'borderRadius': '5px', 'border': '1px solid #ccc', 'marginBottom': '15px'}),

            html.Label("Last Digit Prediction", style={'fontWeight': 'bold', 'fontSize': '12px'}),
            html.Div([
                html.Button("Over 2", id='btn-mode-over', style={'flex': '1', 'padding': '10px', 'backgroundColor': '#00a79e', 'color': 'white', 'border': 'none', 'borderRadius': '5px 0 0 5px'}),
                html.Button("Under 7", id='btn-mode-under', style={'flex': '1', 'padding': '10px', 'backgroundColor': '#eee', 'border': '1px solid #ccc', 'borderRadius': '0 5px 5px 0'})
            ], style={'display': 'flex', 'marginBottom': '20px'}),

            # SMART ACTION BUTTONS
            html.Button([
                html.Div("SMART PURCHASE", style={'fontSize': '14px', 'fontWeight': 'bold'}),
                html.Div("Checks Logic Before Buying", style={'fontSize': '10px', 'opacity': '0.8'})
            ], id='btn-buy', style={'width': '100%', 'padding': '15px', 'backgroundColor': STYLE_GREEN, 'color': 'white', 'border': 'none', 'borderRadius': '5px', 'cursor': 'pointer', 'marginBottom': '10px'}),

            html.Div(id='trade-feedback', style={'textAlign': 'center', 'marginTop': '10px', 'fontWeight': 'bold'}),
            
            # Hidden inputs for Tokens
            dcc.Input(id='token-demo', type='hidden', value=DEFAULT_TOKEN_DEMO),
            dcc.Input(id='token-real', type='hidden', value=DEFAULT_TOKEN_REAL),

        ], style={'flex': '1', 'backgroundColor': STYLE_SIDEBAR, 'padding': '20px'})

    ], style={'flex': '1', 'display': 'flex'}),

    dcc.Interval(id='ui-update', interval=1000, n_intervals=0)
])

# --- LOGIC ENGINE ---
async def check_and_trade(api, contract_type, barrier, stake, mode):
    global data_store
    
    # 1. RUN ANALYSIS
    stats = data_store['digit_stats']
    prev = data_store['prev_stats']
    ranks = data_store['ranks']
    
    # Logic: Over 2
    cond_under_10 = all(stats[i] < 10.0 for i in [0, 1, 2])
    extremes = [ranks.get('least'), ranks.get('second_least'), ranks.get('most')]
    cond_not_extremes = (0 not in extremes) and (1 not in extremes) and (2 not in extremes)
    cond_decreasing = all(stats[i] <= prev[i] for i in [0, 1, 2])
    
    is_safe = cond_under_10 and cond_not_extremes and cond_decreasing
    
    if not is_safe:
        reasons = []
        if not cond_under_10: reasons.append("0,1,2 > 10%")
        if not cond_not_extremes: reasons.append("0,1,2 is Highest/Lowest")
        if not cond_decreasing: reasons.append("0,1,2 Rising")
        return False, f"⛔ UNSAFE: {', '.join(reasons)}"

    # 2. EXECUTE IF SAFE
    try:
        proposal = await api.proposal({"proposal": 1, "amount": stake, "barrier": barrier, "basis": "stake", "contract_type": contract_type, "currency": "USD", "duration": 1, "duration_unit": "t", "symbol": data_store['symbol']})
        buy = await api.buy({"buy": proposal['proposal']['id'], "price": stake})
        
        return True, f"✅ BOUGHT {contract_type}! (ID: {buy['buy']['contract_id']})"
    except Exception as e:
        return False, f"Error: {str(e)}"

# --- BACKEND ---
def update_statistics():
    if len(data_store['digits']) > 0:
        counts = Counter(data_store['digits'])
        total = len(data_store['digits'])
        stats = {i: (counts.get(i, 0) / total) * 100 for i in range(10)}
        
        if len(data_store['digits']) % 10 == 0:
            data_store['prev_stats'] = data_store['digit_stats'].copy()
        
        data_store['digit_stats'] = stats
        # Rank Logic
        sorted_digits = sorted(stats, key=stats.get)
        data_store['ranks'] = {'least': sorted_digits[0], 'second_least': sorted_digits[1], 'most': sorted_digits[-1]}

async def run_system():
    global data_store
    api = None
    while True:
        try:
            if api is None:
                api = DerivAPI(app_id=APP_ID)
                token = DEFAULT_TOKEN_REAL if data_store['account_type'] == 'real' else DEFAULT_TOKEN_DEMO
                if not token: await asyncio.sleep(1); continue
                
                await api.authorize(token)
                
                # FETCH HISTORY (BLOCKING)
                hist = await api.ticks_history({'ticks_history': data_store['symbol'], 'count': 1000, 'end': 'latest', 'style': 'ticks'})
                data_store['digits'] = deque([int(str(p)[-1]) for p in hist['history']['prices']], maxlen=1000)
                data_store['prices'] = deque(hist['history']['prices'], maxlen=1000)
                data_store['times'] = deque([datetime.fromtimestamp(t) for t in hist['history']['times']], maxlen=1000)
                
                update_statistics()
                data_store['is_ready'] = True # UNLOCK UI
                
                # LIVE STREAM
                stream = await api.subscribe({'ticks': data_store['symbol']})
                loop = asyncio.get_running_loop()
                stream.subscribe(lambda t: process_tick(t))
            
            if api:
                try: 
                    bal = await api.balance()
                    data_store['balance'] = f"${bal['balance']['balance']}"
                except: pass
            
            await asyncio.sleep(2)
        except: api = None; await asyncio.sleep(2)

def process_tick(tick):
    try:
        quote = float(tick['tick']['quote'])
        epoch = int(tick['tick']['epoch'])
        digit = int(str(quote)[-1])
        
        data_store['digits'].append(digit)
        data_store['prices'].append(quote)
        data_store['times'].append(datetime.fromtimestamp(epoch))
        update_statistics()
    except: pass

# --- CALLBACKS ---
@app.callback(
    [Output('main-chart', 'figure'),
     Output('deriv-circles', 'children'),
     Output('live-balance', 'children'),
     Output('logic-status-box', 'children'),
     Output('trade-feedback', 'children')],
    [Input('ui-update', 'n_intervals'),
     Input('btn-buy', 'n_clicks')],
    [State('market-selector', 'value'),
     State('account-type', 'value'),
     State('stake-input', 'value')]
)
def update_ui(n, btn_buy, market, acc, stake):
    trigger = ctx.triggered_id
    data_store['symbol'] = market
    data_store['account_type'] = acc

    # 1. HANDLE BUY CLICK
    feedback = ""
    if trigger == 'btn-buy':
        loop = asyncio.new_event_loop()
        api = DerivAPI(app_id=APP_ID) # Temp API for execution
        async def quick_trade():
            await api.authorize(DEFAULT_TOKEN_REAL if acc == 'real' else DEFAULT_TOKEN_DEMO)
            return await check_and_trade(api, "DIGITOVER", "2", float(stake), "OVER")
        
        success, msg = loop.run_until_complete(quick_trade())
        feedback = html.Div(msg, style={'color': 'green' if success else 'red'})
        loop.close()

    # 2. CHART (Deriv Style - Area)
    fig = go.Figure()
    if data_store['is_ready']:
        fig.add_trace(go.Scatter(
            x=list(data_store['times'])[-50:], 
            y=list(data_store['prices'])[-50:],
            fill='tozeroy',
            mode='lines+markers',
            line=dict(color='#888', width=1),
            marker=dict(size=4, color='#cc0000'), # Red dot for tick
            fillcolor='rgba(200,200,200,0.2)'
        ))
    fig.update_layout(
        margin=dict(l=40, r=20, t=20, b=20),
        plot_bgcolor='white', paper_bgcolor='white',
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor='#eee')
    )

    # 3. CIRCLES
    stats = data_store['digit_stats']
    circles = []
    for d in range(10):
        p = stats.get(d, 0)
        # Deriv Color Logic
        c = '#333' # Default Text
        bg = '#fff'
        border = '2px solid #ccc'
        
        if d <= 2: bg = '#fffbe6'; border = '2px solid #ffe58f' # Yellow Zone
        
        # Heatmap Colors
        bar_h = p * 3 # Height based on %
        bar_c = '#00a79e' # Blueish
        if p >= 12: bar_c = '#008832' # Green
        if p <= 8: bar_c = '#cc0000'  # Red

        circles.append(html.Div([
            html.Div(f"{p:.1f}%", style={'fontSize': '10px', 'color': bar_c, 'fontWeight': 'bold'}),
            html.Div(style={'height': f'{bar_h}px', 'width': '6px', 'backgroundColor': bar_c, 'borderRadius': '3px', 'margin': '2px 0'}),
            html.Div(str(d), style={'width': '24px', 'height': '24px', 'borderRadius': '50%', 'border': border, 'backgroundColor': bg, 'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center', 'fontSize': '12px', 'fontWeight': 'bold'})
        ], style={'display': 'flex', 'flexDirection': 'column', 'alignItems': 'center', 'margin': '0 5px', 'justifyContent': 'flex-end', 'height': '100%'}))

    # 4. LOGIC BOX
    if not data_store['is_ready']:
        logic_msg = "⏳ LOADING 1000 TICKS..."
    else:
        # Check Logic for display
        cond_under_10 = all(stats[i] < 10.0 for i in [0, 1, 2])
        ranks = data_store['ranks']
        extremes = [ranks.get('least'), ranks.get('second_least'), ranks.get('most')]
        cond_not_extremes = (0 not in extremes) and (1 not in extremes) and (2 not in extremes)
        cond_decreasing = all(stats[i] <= data_store['prev_stats'][i] for i in [0, 1, 2])

        logic_msg = html.Div([
            html.Div(f"{'✅' if cond_under_10 else '❌'} Lows < 10% (0: {stats[0]:.1f}%, 1: {stats[1]:.1f}%, 2: {stats[2]:.1f}%)"),
            html.Div(f"{'✅' if cond_not_extremes else '❌'} Not Extremes (Least: {ranks.get('least')})"),
            html.Div(f"{'✅' if cond_decreasing else '❌'} Trends Dropping"),
            html.Div("READY TO TRADE" if (cond_under_10 and cond_not_extremes and cond_decreasing) else "WAITING...", style={'fontWeight': 'bold', 'marginTop': '10px', 'color': 'green' if cond_under_10 and cond_not_extremes and cond_decreasing else 'red'})
        ])

    return fig, circles, data_store['balance'], logic_msg, feedback

# --- THREAD ---
def start_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_system())

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=start_loop, args=(loop,))
    t.daemon = True
    t.start()
    app.run(host='0.0.0.0', port=8050, debug=False)
