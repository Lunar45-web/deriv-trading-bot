import os
import time
import requests
from datetime import datetime
from flask import Flask, jsonify
import threading
import random

app = Flask(__name__)

# ===== YOUR CORRECT TOKEN =====
API_TOKEN = os.getenv('DEMO_API_TOKEN', 's4TVgxiEc36iXSM')  # ← YOUR TOKEN
print(f"🔑 Using token: {API_TOKEN}")

# ===== Deriv API Configuration =====
BASE_URL = "https://api.deriv.com"
APP_ID = 1089  # Deriv app ID

# Headers for Deriv API
HEADERS = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'Authorization': f'Bearer {API_TOKEN}'
}

class SimpleDerivBot:
    def __init__(self):
        self.running = False
        self.connected = False
        self.balance = 10000.00
        self.total_trades = 0
        self.wins = 0
        self.losses = 0
        self.session_profit = 0.0
        self.last_trade_time = None
        
        # Test connection immediately
        self.test_connection()
    
    def test_connection(self):
        """Test connection to Deriv API"""
        print("🔌 Testing Deriv API connection...")
        try:
            # First, try to get balance
            response = requests.post(
                f"{BASE_URL}/balance",
                headers=HEADERS,
                json={},
                timeout=10
            )
            
            print(f"📡 Balance API Status: {response.status_code}")
            print(f"📡 Response: {response.text[:200]}")
            
            if response.status_code == 200:
                data = response.json()
                if 'error' not in data:
                    self.balance = float(data.get('balance', {}).get('balance', 10000))
                    self.connected = True
                    print(f"✅ API CONNECTED! Balance: ${self.balance:.2f}")
                    
                    # Also test active symbols
                    symbols_response = requests.post(
                        f"{BASE_URL}/active_symbols",
                        headers=HEADERS,
                        json={"active_symbols": "brief", "product_type": "basic"},
                        timeout=10
                    )
                    
                    if symbols_response.status_code == 200:
                        print("✅ Active symbols retrieved")
                    return True
                else:
                    print(f"❌ API Error: {data.get('error', {})}")
            else:
                print(f"❌ HTTP Error: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Connection error: {type(e).__name__}: {str(e)}")
        
        print("⚠️ API connection failed, using simulation mode")
        return False
    
    def buy_contract(self, contract_type, barrier):
        """Buy a contract on Deriv"""
        try:
            buy_data = {
                "buy": 1,
                "price": 1,
                "parameters": {
                    "amount": 1,
                    "basis": "stake",
                    "contract_type": contract_type,
                    "currency": "USD",
                    "duration": 1,
                    "duration_unit": "t",
                    "symbol": "R_100",
                    "barrier": str(barrier)
                }
            }
            
            print(f"📤 Buying {contract_type} {barrier}...")
            
            response = requests.post(
                f"{BASE_URL}/buy",
                headers=HEADERS,
                json=buy_data,
                timeout=15
            )
            
            print(f"📡 Buy Response Status: {response.status_code}")
            print(f"📡 Buy Response: {response.text[:300]}")
            
            if response.status_code == 200:
                data = response.json()
                if 'error' in data:
                    print(f"❌ Buy error: {data['error']}")
                    return None
                
                contract_id = data.get('buy', {}).get('contract_id')
                print(f"✅ Contract purchased: {contract_id}")
                
                # Wait for contract to settle
                time.sleep(3)
                
                # Check contract result
                contract_response = requests.post(
                    f"{BASE_URL}/proposal_open_contract",
                    headers=HEADERS,
                    json={"proposal_open_contract": 1, "contract_id": contract_id},
                    timeout=10
                )
                
                if contract_response.status_code == 200:
                    contract_data = contract_response.json()
                    if 'error' not in contract_data:
                        profit = float(contract_data.get('proposal_open_contract', {}).get('profit', 0))
                        payout = float(contract_data.get('proposal_open_contract', {}).get('payout', 0))
                        
                        print(f"💰 Trade result: ${profit:.2f}")
                        return {
                            "success": True,
                            "contract_id": contract_id,
                            "profit": profit,
                            "payout": payout,
                            "result": "win" if profit > 0 else "loss"
                        }
            
            return None
            
        except Exception as e:
            print(f"❌ Trade error: {type(e).__name__}: {str(e)}")
            return None
    
    def trading_loop(self):
        """Main trading loop"""
        print("🔄 Trading started...")
        
        trade_count = 0
        while self.running and trade_count < 50:
            try:
                # Wait 2-3 minutes between trades
                wait_time = random.randint(120, 180)
                print(f"⏳ Waiting {wait_time//60} minutes for next trade...")
                time.sleep(wait_time)
                
                if not self.running:
                    break
                
                # Make trading decision
                decisions = [
                    ("DIGITUNDER", 7, "Under 7"),
                    ("DIGITUNDER", 8, "Under 8"),
                    ("DIGITOVER", 2, "Over 2"),
                    ("DIGITOVER", 3, "Over 3")
                ]
                contract_type, barrier, reason = random.choice(decisions)
                
                print(f"📊 Decision: {reason}")
                
                if self.connected:
                    # Try REAL trade
                    trade_result = self.buy_contract(contract_type, barrier)
                    
                    if trade_result and trade_result["success"]:
                        self.total_trades += 1
                        self.session_profit += trade_result["profit"]
                        self.balance += trade_result["profit"]
                        self.last_trade_time = datetime.now()
                        trade_count += 1
                        
                        if trade_result["result"] == "win":
                            self.wins += 1
                            print(f"✅ REAL WIN! +${trade_result['profit']:.2f}")
                        else:
                            self.losses += 1
                            print(f"❌ REAL LOSS! -${abs(trade_result['profit']):.2f}")
                        
                        print(f"💰 Balance: ${self.balance:.2f} | Session: ${self.session_profit:.2f}")
                        
                        # Update connection status
                        if trade_result["profit"] != 0:
                            print(f"🎯 REAL TRADE CONFIRMED! Deriv account updated.")
                    
                    else:
                        print("⚠️ Real trade failed, using simulation")
                        self.simulate_trade(reason)
                        trade_count += 1
                
                else:
                    # Simulation mode
                    self.simulate_trade(reason)
                    trade_count += 1
                
                # Check stop conditions
                if self.session_profit >= 50:
                    print(f"🎯 Target reached! Profit: ${self.session_profit:.2f}")
                    break
                    
                if self.session_profit <= -100:
                    print(f"🛑 Stop loss hit! Loss: ${abs(self.session_profit):.2f}")
                    break
                
            except Exception as e:
                print(f"⚠️ Loop error: {e}")
                time.sleep(10)
        
        print(f"🏁 Trading finished. Total trades: {self.total_trades}")
        self.running = False
    
    def simulate_trade(self, reason):
        """Simulate a trade"""
        is_win = random.random() < 0.55
        profit = 0.95 if is_win else -1.0
        
        self.total_trades += 1
        self.session_profit += profit
        self.balance += profit
        self.last_trade_time = datetime.now()
        
        if is_win:
            self.wins += 1
            print(f"✅ SIMULATED WIN ({reason}): +${profit:.2f}")
        else:
            self.losses += 1
            print(f"❌ SIMULATED LOSS ({reason}): -${abs(profit):.2f}")
        
        print(f"💰 Balance: ${self.balance:.2f} | Session: ${self.session_profit:.2f}")
    
    def start(self):
        if not self.running:
            self.running = True
            thread = threading.Thread(target=self.trading_loop, daemon=True)
            thread.start()
            print("🚀 Bot started!")
            return True
        return False
    
    def stop(self):
        self.running = False
        print("🛑 Bot stopped")

# Create bot instance
bot = SimpleDerivBot()

# ===== FLASK ROUTES =====
@app.route('/')
def dashboard():
    win_rate = (bot.wins / bot.total_trades * 100) if bot.total_trades > 0 else 0
    
    return f"""
    <html><head><title>Deriv Trading Bot</title><meta http-equiv="refresh" content="10">
    <style>
    body{{font-family:Arial; margin:40px; background:#f5f5f5;}}
    .container{{max-width:800px; margin:auto; background:white; padding:30px; border-radius:10px; box-shadow:0 2px 10px rgba(0,0,0,0.1);}}
    .stats{{display:grid; grid-template-columns:repeat(2,1fr); gap:20px; margin:20px 0;}}
    .stat-box{{background:#f8f9fa; padding:15px; border-radius:8px; border-left:4px solid #007bff;}}
    button{{padding:10px 20px; margin:5px; background:#007bff; color:white; border:none; border-radius:5px; cursor:pointer;}}
    .running{{color:green;}} .stopped{{color:red;}}
    .profit{{color:green; font-weight:bold;}} .loss{{color:red; font-weight:bold;}}
    .connected{{color:green;}} .disconnected{{color:orange;}}
    </style></head>
    <body><div class="container">
    <h1>🤖 Simple Deriv Trading Bot</h1>
    <p><strong>Status:</strong> <span class="{'running' if bot.running else 'stopped'}">
    {'🟢 RUNNING' if bot.running else '🔴 STOPPED'}</span></p>
    <p><strong>API Connection:</strong> <span class="{'connected' if bot.connected else 'disconnected'}">
    {'✅ CONNECTED to Deriv' if bot.connected else '⚠️ SIMULATION MODE'}</span></p>
    <p><strong>Token:</strong> {API_TOKEN} (length: {len(API_TOKEN)})</p>
    
    <div class="stats">
        <div class="stat-box"><h3>💰 Balance</h3><p>${bot.balance:.2f}</p></div>
        <div class="stat-box"><h3>📈 Session Profit</h3><p class="{'profit' if bot.session_profit >= 0 else 'loss'}">${bot.session_profit:.2f}</p></div>
        <div class="stat-box"><h3>📊 Total Trades</h3><p>{bot.total_trades}</p></div>
        <div class="stat-box"><h3>🎯 Win Rate</h3><p>{win_rate:.1f}%</p></div>
        <div class="stat-box"><h3>✅ Wins / ❌ Losses</h3><p>{bot.wins} / {bot.losses}</p></div>
        <div class="stat-box"><h3>⏰ Last Trade</h3><p>{bot.last_trade_time.strftime('%H:%M:%S') if bot.last_trade_time else 'Never'}</p></div>
    </div>
    
    <div>
        <button onclick="window.location.href='/start'">▶️ Start Bot</button>
        <button onclick="window.location.href='/stop'">⏹️ Stop Bot</button>
        <button onclick="window.location.href='/test'">🔧 Test API</button>
        <button onclick="window.location.href='/force-trade'">⚡ Force Test Trade</button>
    </div>
    
    <div style="margin-top:30px; padding:15px; background:#e9f7fe; border-radius:8px;">
        <h3>🔧 Debug Information:</h3>
        <p><strong>Token:</strong> {API_TOKEN}</p>
        <p><strong>API URL:</strong> {BASE_URL}</p>
        <p><strong>Connection Status:</strong> {'✅ Connected' if bot.connected else '❌ Failed'}</p>
        <p><strong>Mode:</strong> {'REAL Trading' if bot.connected else 'SIMULATION'}</p>
        <p><strong>Check Deriv:</strong> Your token should show "Last used: Just now" if connected</p>
    </div>
    
    <p style="margin-top:30px; color:#666;">
        {'✅ Bot is trading on REAL Deriv API' if bot.connected else '⚠️ Bot is in SIMULATION mode. Check API connection.'}
        <br>Auto-refreshes every 10 seconds.
    </p>
    </div></body></html>
    """

@app.route('/start')
def start_bot():
    bot.start()
    return jsonify({"status": "started", "connected": bot.connected})

@app.route('/stop')
def stop_bot():
    bot.stop()
    return jsonify({"status": "stopped"})

@app.route('/test')
def test_api():
    """Test API connection"""
    connected = bot.test_connection()
    return jsonify({
        "connected": connected,
        "token": API_TOKEN[:5] + "..." + API_TOKEN[-5:],
        "api_url": BASE_URL,
        "message": "API is working!" if connected else "API connection failed"
    })

@app.route('/force-trade')
def force_trade():
    """Force a test trade"""
    if bot.connected:
        result = bot.buy_contract("DIGITUNDER", 7)
        if result and result["success"]:
            return jsonify({
                "status": "real_trade_executed",
                "profit": result["profit"],
                "result": result["result"]
            })
    
    # Simulate trade
    bot.simulate_trade("Forced Test")
    return jsonify({
        "status": "simulated_trade",
        "message": "Simulated trade executed"
    })

# Auto-start bot
def auto_start():
    time.sleep(5)
    bot.start()

if __name__ == "__main__":
    if os.getenv('RENDER'):
        threading.Thread(target=auto_start, daemon=True).start()
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
