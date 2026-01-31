import asyncio
import os
import threading
import pandas as pd
import plotly.graph_objs as go
from collections import deque, Counter
from datetime import datetime
from dash import Dash, dcc, html, Input, Output, State, ctx, dash_table
from deriv_api import DerivAPI

# --- CONFIGURATION ---
DEFAULT_TOKEN_DEMO = os.getenv('DERIV_TOKEN_DEMO', 's4TVgxiEc36iXSM') 
DEFAULT_TOKEN_REAL = os.getenv('DERIV_TOKEN_REAL', '') 
APP_ID = 1089

# --- GLOBAL DATA ---
data_store = {
    'symbol': 'R_100', 
    'times': deque(maxlen=1000),
    'digits': deque(maxlen=1000), 
    
    'balance': "Waiting...",
    'status': "Ready...",
    'active': False, 
    'account_type': 'demo', 
    
    # Logic Inspection
    'digit_stats': {i: 0 for i in range(10)},
    'prev_stats': {i: 0 for i in range(10)}, # For Trend Analysis
    'ranks': {}, # To check "Least" and "2nd Least"
    
    'logic_state': {
        'cond_under_10': False,
        'cond_not_extremes': False,
        'cond_decreasing': False,
        'ready': False
    },
    
    'trade_log': deque(maxlen=10),
    'current_profit': 0.0,
    'consecutive_losses': 0,
    'is_trading': False, 
    
    'stake': 2.0, 'target': 20.0, 'stop_loss': 50.0,
    'martingale': True, 'martingale_multiplier': 2.5
}

# --- DASHBOARD ---
app = Dash(__name__)
server = app.server

app.layout = html.Div(style={'backgroundColor': '#0a0a0a', 'color': '#e0e0e0', 'fontFamily': 'Roboto, monospace', 'minHeight': '100vh'}, children=[
    
    # HEADER
    html.Div([
        html.H2("DERIV PERFORMANCE MONITOR", style={'color': '#00ff88', 'margin': '0'}),
        html.Div([
            html.H3(id='live-balance', children="---", style={'color': '#fff', 'margin': '0'}),
            html.Div(id='live-profit', children="$0.00", style={'color': '#00ccff', 'fontSize': '16px'})
        ], style={'textAlign': 'right'})
    ], style={'display': 'flex', 'justifyContent': 'space-between', 'padding': '15px 20px', 'backgroundColor': '#111', 'borderBottom': '1px solid #333'}),

    html.Div([
        # CONTROLS
        html.Div([
            html.Label("ACCOUNT", style={'color': '#888', 'fontSize': '10px'}),
            dcc.RadioItems(id='account-type', options=[{'label': 'DEMO', 'value': 'demo'}, {'label': 'REAL', 'value': 'real'}], value='demo', inline=True, style={'marginBottom': '15px'}),
            
            html.Label("TOKENS", style={'color': '#888', 'fontSize': '10px'}),
            dcc.Input(id='token-demo', placeholder="Demo Token", value=DEFAULT_TOKEN_DEMO, style={'width': '100%', 'marginBottom': '5px', 'backgroundColor': '#222', 'color': '#fff', 'border': 'none'}),
            dcc.Input(id='token-real', placeholder="Real Token", value=DEFAULT_TOKEN_REAL, style={'width': '100%', 'marginBottom': '15px', 'backgroundColor': '#222', 'color': '#fff', 'border': 'none'}),

            html.Label("SETTINGS", style={'color': '#888', 'fontSize': '10px'}),
            html.Div([html.Label("Stake:"), dcc.Input(id='stake-input', type='number', value=2.0, style={'width': '50px', 'float': 'right'})], style={'marginBottom': '5px'}),
            html.Div([html.Label("Target:"), dcc.Input(id='target-input', type='number', value=20.0, style={'width': '50px', 'float': 'right'})], style={'marginBottom': '5px'}),
            html.Div([html.Label("Stop Loss:"), dcc.Input(id='stop-input', type='number', value=50.0, style={'width': '50px', 'float': 'right'})], style={'marginBottom': '20px'}),

            html.Button('START', id='btn-start', style={'width': '100%', 'padding': '12px', 'backgroundColor': '#00ff88', 'border': 'none', 'fontWeight': 'bold', 'cursor': 'pointer', 'marginBottom': '10px'}),
            html.Button('STOP', id='btn-stop', style={'width': '100%', 'padding': '12px', 'backgroundColor': '#ff3333', 'color': '#fff', 'border': 'none', 'fontWeight': 'bold', 'cursor': 'pointer'}),

            html.Div(id='control-feedback', style={'fontSize': '10px', 'color': 'yellow', 'marginTop': '10px'})

        ], style={'width': '220px', 'padding': '20px', 'backgroundColor': '#111'}),

        # MAIN PANEL
        html.Div([
            
            # 1. LOGIC CHECKLIST (Top)
            html.Div(id='logic-checklist', style={'display': 'flex', 'justifyContent': 'space-around', 'marginBottom': '20px', 'padding': '10px', 'backgroundColor': '#1a1a1a', 'borderRadius': '5px'}),

            # 2. REAL-TIME DIGIT MONITOR (The Request)
            html.H4("LIVE DIGIT PERFORMANCE (1000 Ticks)", style={'margin': '0 0 10px 0', 'color': '#ccc', 'fontSize': '14px'}),
            html.Div(id='performance-table'),

            # 3. STATUS BAR
            html.Div(id='main-status', children="Status: Idle", style={'margin': '20px 0', 'padding': '15px', 'backgroundColor': '#222', 'color': '#ffa500', 'textAlign': 'center', 'fontWeight': 'bold', 'borderRadius': '5px'}),
            
            # 4. TRADE LOG
            html.Div(id='trade-log-table'),

            dcc.Interval(id='ui-update', interval=1000, n_intervals=0)

        ], style={'flex': '1', 'padding': '20px', 'overflowY': 'auto'})

    ], style={'display': 'flex', 'height': 'calc(100vh - 60px)'})
])

# --- TRADING EXECUTION ---
async def execute_trade(api, contract_type, prediction):
    global data_store
    if not data_store['active']: return
    
    # Limits
    if data_store['current_profit'] >= data_store['target'] or data_store['current_profit'] <= -data_store['stop_loss']:
        data_store['active'] = False
        data_store['status'] = "🛑 LIMIT REACHED"
        return

    stake = data_store['stake']
    if data_store['martingale'] and data_store['consecutive_losses'] > 0:
        stake = round(stake * data_store['martingale_multiplier'], 2)

    try:
        data_store['status'] = f"⚡ FIRING: {prediction} (${stake})"
        data_store['is_trading'] = True 
        
        proposal = await api.proposal({"proposal": 1, "amount": stake, "barrier": "2", "basis": "stake", "contract_type": contract_type, "currency": "USD", "duration": 1, "duration_unit": "t", "symbol": data_store['symbol']})
        buy = await api.buy({"buy": proposal['proposal']['id'], "price": stake})
        contract_id = buy['buy']['contract_id']
        
        trade_rec = {'Time': datetime.now().strftime("%H:%M:%S"), 'Stake': stake, 'Result': '...', 'Profit': 0}
        data_store['trade_log'].appendleft(trade_rec)
        
        await asyncio.sleep(2.5) 
        
        profit_table = await api.profit_table({"description": 1, "limit": 1})
        if profit_table['profit_table']['transactions']:
            latest = profit_table['profit_table']['transactions'][0]
            if latest['contract_id'] == contract_id:
                profit = float(latest['sell_price']) - float(latest['buy_price'])
                data_store['current_profit'] += profit
                
                data_store['trade_log'][0]['Result'] = 'WIN' if profit > 0 else 'LOSS'
                data_store['trade_log'][0]['Profit'] = f"${profit:.2f}"
                
                if profit > 0:
                    data_store['consecutive_losses'] = 0
                    data_store['status'] = f"✅ WIN (+${profit:.2f})"
                else:
                    data_store['consecutive_losses'] += 1
                    data_store['status'] = f"❌ LOSS (-${stake})"
        
        data_store['is_trading'] = False
    except Exception as e:
        print(f"Error: {e}")
        data_store['is_trading'] = False

def update_statistics():
    if len(data_store['digits']) > 0:
        counts = Counter(data_store['digits'])
        total = len(data_store['digits'])
        
        # Current Stats
        stats = {i: (counts.get(i, 0) / total) * 100 for i in range(10)}
        
        # Update Trend Memory every 10 ticks
        if len(data_store['digits']) % 10 == 0:
            data_store['prev_stats'] = data_store['digit_stats'].copy()
            
        data_store['digit_stats'] = stats
        
        # Calculate Ranks (For "Least" and "2nd Least" logic)
        # Sort digits by percentage (Lowest to Highest)
        sorted_digits = sorted(stats, key=stats.get)
        
        data_store['ranks'] = {
            'least': sorted_digits[0],       # The absolute lowest
            'second_least': sorted_digits[1], # The 2nd lowest
            'most': sorted_digits[-1]        # The highest (Green bar)
        }

def process_tick(tick, api, loop):
    global data_store
    try:
        last_digit = int(str(tick['tick']['quote'])[-1])
        data_store['digits'].append(last_digit)
        update_statistics()

        stats = data_store['digit_stats']
        ranks = data_store['ranks']
        prev = data_store['prev_stats']
        
        # --- THE USER'S STRICT LOGIC ---
        
        # 1. Strictly Under 10% (9.9% or lower)
        cond_under_10 = all(stats[i] < 10.0 for i in [0, 1, 2])
        
        # 2. Not Extremes (Not Least, Not 2nd Least, Not Most)
        extremes = [ranks['least'], ranks['second_least'], ranks['most']]
        cond_not_extremes = (0 not in extremes) and (1 not in extremes) and (2 not in extremes)
        
        # 3. Decreasing Trend (Current % < Previous %)
        cond_decreasing = all(stats[i] <= prev[i] for i in [0, 1, 2])
        
        # 4. Ready Status
        is_ready = cond_under_10 and cond_not_extremes and cond_decreasing
        
        data_store['logic_state'] = {
            'cond_under_10': cond_under_10,
            'cond_not_extremes': cond_not_extremes,
            'cond_decreasing': cond_decreasing,
            'ready': is_ready
        }

        # Status Message Logic
        if data_store['active'] and not data_store['is_trading']:
            if not cond_under_10:
                data_store['status'] = "Waiting: 0, 1, or 2 is above 10%"
            elif not cond_not_extremes:
                data_store['status'] = f"Waiting: 0, 1, or 2 is an Extreme (Lowest: {ranks['least']})"
            elif not cond_decreasing:
                data_store['status'] = "Waiting: 0, 1, or 2 is Rising"
            elif is_ready:
                data_store['status'] = "⚠️ PERFECT SETUP: Waiting for Trigger (0, 1, 2)..."
        
        # TRIGGER
        if data_store['active'] and not data_store['is_trading']:
            if is_ready and last_digit <= 2:
                asyncio.run_coroutine_threadsafe(execute_trade(api, "DIGITOVER", "Strict Sniper"), loop)

    except Exception as e:
        print(f"Tick Error: {e}")

# --- RUNNER ---
async def run_trader_loop():
    global data_store
    api = None
    while True:
        try:
            if api is None:
                api = DerivAPI(app_id=APP_ID)
                token = DEFAULT_TOKEN_REAL if data_store['account_type'] == 'real' else DEFAULT_TOKEN_DEMO
                if not token: await asyncio.sleep(2); continue
                await api.authorize(token)
                
                # Fetch History (1000 Ticks)
                hist = await api.ticks_history({'ticks_history': data_store['symbol'], 'count': 1000, 'end': 'latest', 'style': 'ticks'})
                data_store['digits'] = deque([int(str(p)[-1]) for p in hist['history']['prices']], maxlen=1000)
                update_statistics()
                
                stream = await api.subscribe({'ticks': data_store['symbol']})
                loop = asyncio.get_running_loop()
                stream.subscribe(lambda t: process_tick(t, api, loop))
            
            if api: 
                try: 
                    bal = await api.balance()
                    data_store['balance'] = f"${bal['balance']['balance']}"
                except: pass
            await asyncio.sleep(2)
        except: api = None; await asyncio.sleep(5)

# --- UI CALLBACKS ---
@app.callback(
    [Output('live-balance', 'children'), Output('live-profit', 'children'),
     Output('main-status', 'children'), Output('performance-table', 'children'),
     Output('logic-checklist', 'children'), Output('trade-log-table', 'children'),
     Output('control-feedback', 'children')],
    [Input('ui-update', 'n_intervals'), Input('btn-start', 'n_clicks'), Input('btn-stop', 'n_clicks')],
    [State('account-type', 'value'), State('stake-input', 'value'), State('target-input', 'value'), 
     State('stop-input', 'value'), State('token-demo', 'value'), State('token-real', 'value')]
)
def update_ui(n, start, stop, acc, stake, target, sl, t_demo, t_real):
    ctx_msg = ctx.triggered_id
    if ctx_msg == 'btn-start': data_store['active'] = True
    elif ctx_msg == 'btn-stop': data_store['active'] = False
    
    data_store['stake'] = float(stake or 2)
    data_store['target'] = float(target or 20)
    data_store['stop_loss'] = float(sl or 50)
    data_store['account_type'] = acc
    global DEFAULT_TOKEN_DEMO, DEFAULT_TOKEN_REAL
    DEFAULT_TOKEN_DEMO, DEFAULT_TOKEN_REAL = t_demo, t_real

    # 1. PERFORMANCE MONITOR TABLE
    stats = data_store['digit_stats']
    prev = data_store['prev_stats']
    ranks = data_store['ranks']
    
    rows = [html.Tr([html.Th("Digit"), html.Th("Percentage"), html.Th("Trend"), html.Th("Rank Status")], style={'color': '#888', 'fontSize': '12px'})]
    
    for d in range(10):
        p = stats.get(d, 0)
        trend = "🔺 Rising" if p > prev.get(d, 0) else "🔻 Dropping" if p < prev.get(d, 0) else "➡ Flat"
        trend_color = '#ff3333' if "Rising" in trend and d<=2 else '#00ff88' if "Dropping" in trend and d<=2 else '#888'
        
        # Rank Logic
        rank_text = "Mid"
        rank_color = '#888'
        if d == ranks.get('least'): rank_text = "⚠️ LOWEST"; rank_color = '#ff3333'
        elif d == ranks.get('second_least'): rank_text = "⚠️ 2nd LOW"; rank_color = '#ffaa00'
        elif d == ranks.get('most'): rank_text = "👑 HIGHEST"; rank_color = '#00ff88'
        
        # Highlight 0-2
        bg = '#222'
        if d <= 2:
            bg = '#1a1a2e'
            if p >= 10.0: rank_text += " (TOO HIGH)"; rank_color = '#ff3333'
        
        rows.append(html.Tr([
            html.Td(str(d), style={'fontWeight': 'bold', 'color': '#fff'}),
            html.Td(f"{p:.1f}%", style={'color': '#fff'}),
            html.Td(trend, style={'color': trend_color, 'fontSize': '11px'}),
            html.Td(rank_text, style={'color': rank_color, 'fontSize': '11px', 'fontWeight': 'bold'})
        ], style={'backgroundColor': bg}))
    
    perf_table = html.Table(rows, style={'width': '100%', 'borderCollapse': 'collapse'})

    # 2. LOGIC CHECKLIST
    logic = data_store['logic_state']
    def item(label, ok): return html.Div(f"{'✅' if ok else '⏳'} {label}", style={'color': '#00ff88' if ok else '#666', 'fontSize': '12px'})
    checklist = [
        item("All 0,1,2 < 10%", logic['cond_under_10']),
        item("Not Lowest/2nd Lowest", logic['cond_not_extremes']),
        item("Trend Decreasing", logic['cond_decreasing']),
        item("READY TO FIRE", logic['ready'])
    ]

    # 3. TRADE LOG
    log_rows = []
    for t in data_store['trade_log']:
        c = '#00ff88' if 'WIN' in t['Result'] else '#ff3333' if 'LOSS' in t['Result'] else '#ffff00'
        log_rows.append(html.Tr([html.Td(t['Time']), html.Td(f"${t['Stake']}"), html.Td(t['Result'], style={'color': c}), html.Td(t['Profit'], style={'color': c})], style={'fontSize': '11px'}))
    
    return data_store['balance'], f"${data_store['current_profit']:.2f}", \
           data_store['status'], perf_table, checklist, html.Table(log_rows, style={'width': '100%'}), \
           f"Mode: {acc.upper()}"

def start_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_trader_loop())

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=start_loop, args=(loop,))
    t.daemon = True
    t.start()
    app.run(host='0.0.0.0', port=8050, debug=False)
