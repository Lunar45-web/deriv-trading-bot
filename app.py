import os
import time
import requests
from datetime import datetime
from flask import Flask, jsonify
import threading
import random

app = Flask(__name__)

# ===== CONFIGURATION =====
API_TOKEN = os.getenv('DEMO_API_TOKEN', '')
BASE_URL = "https://deriv-api.crypto.com/v1"

if API_TOKEN:
    HEADERS = {'Authorization': f'Bearer {API_TOKEN}'}
else:
    HEADERS = {}
    print("⚠️ WARNING: No API token found. Running in simulation mode.")

# ===== TRADING BOT =====
class TradingBot:
    def __init__(self):
        self.running = False
        self.total_trades = 0
        self.wins = 0
        self.losses = 0
        self.session_profit = 0.0
        self.last_trade_time = None
        self.stake = 1.0
        self.api_connected = False
        
        if API_TOKEN:
            self.test_api()
    
    def test_api(self):
        """Test API connection"""
        try:
            response = requests.get(f"{BASE_URL}/balance", headers=HEADERS, timeout=5)
            if response.status_code == 200:
                print("✅ API Connected successfully!")
                self.api_connected = True
                return True
            else:
                print(f"❌ API Error {response.status_code}: {response.text}")
                return False
        except Exception as e:
            print(f"❌ API Connection failed: {e}")
            return False
    
    def get_balance(self):
        """Get balance safely"""
        if not self.api_connected:
            return 10000.00  # Default demo balance
        
        try:
            response = requests.get(f"{BASE_URL}/balance", headers=HEADERS, timeout=5)
            if response.status_code == 200:
                data = response.json()
                return data.get('balance', {}).get('balance', 10000.00)
            return 10000.00
        except:
            return 10000.00
    
    def place_trade(self, direction, prediction):
        """Place trade - REAL if API works, otherwise SIMULATE"""
        if not self.api_connected:
            # Simulate trade
            is_win = random.random() < 0.55
            profit = self.stake * 0.95 if is_win else -self.stake
            result = "win" if is_win else "loss"
            
            print(f"📊 SIMULATED: {direction} {prediction} - {result.upper()} ${profit:.2f}")
            return {
                "success": True,
                "result": result,
                "profit": profit,
                "payout": profit if profit > 0 else 0
            }
        
        # REAL TRADE
        try:
            trade_data = {
                "buy": self.stake,
                "price": self.stake,
                "parameters": {
                    "amount": self.stake,
                    "basis": "stake",
                    "contract_type": f"digit{'over' if direction == 'over' else 'under'}",
                    "currency": "USD",
                    "duration": 1,
                    "duration_unit": "t",
                    "symbol": "R_100",
                    "barrier": str(prediction)
                }
            }
            
            response = requests.post(f"{BASE_URL}/buy", json=trade_data, headers=HEADERS, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                contract_id = result.get("buy", {}).get("contract_id")
                
                # Wait and check result
                time.sleep(2)
                check_response = requests.get(
                    f"{BASE_URL}/proposal_open_contract",
                    params={'contract_id': contract_id},
                    headers=HEADERS
                )
                
                if check_response.status_code == 200:
                    contract_data = check_response.json()
                    profit = contract_data.get("proposal_open_contract", {}).get("profit", 0)
                    
                    print(f"✅ REAL TRADE: {direction} {prediction} - ${profit:.2f}")
                    return {
                        "success": True,
                        "result": "win" if profit > 0 else "loss",
                        "profit": profit,
                        "contract_id": contract_id
                    }
            
            print(f"❌ Trade failed: {response.text}")
            return {"success": False, "error": "Trade failed"}
            
        except Exception as e:
            print(f"❌ Trade error: {e}")
            return {"success": False, "error": str(e)}
    
    def trading_loop(self):
        """Main trading loop"""
        print("🔄 Trading started...")
        
        while self.running and self.total_trades < 200:
            try:
                # Wait 2-3 minutes
                wait = random.randint(120, 180)
                print(f"⏳ Next trade in {wait//60} minutes...")
                time.sleep(wait)
                
                if not self.running:
                    break
                
                # Simple decision
                decisions = [
                    ("under", 7, "Under 7 strategy"),
                    ("under", 8, "Under 8 strategy"),
                    ("over", 2, "Over 2 strategy"),
                    ("over", 3, "Over 3 strategy")
                ]
                direction, prediction, reason = random.choice(decisions)
                
                print(f"📊 Decision: {direction.upper()} {prediction} - {reason}")
                
                # Place trade
                trade_result = self.place_trade(direction, prediction)
                
                if trade_result["success"]:
                    self.total_trades += 1
                    self.session_profit += trade_result["profit"]
                    self.last_trade_time = datetime.now()
                    
                    if trade_result["result"] == "win":
                        self.wins += 1
                        print(f"✅ WIN! +${trade_result['profit']:.2f}")
                    else:
                        self.losses += 1
                        print(f"❌ LOSS! -${abs(trade_result['profit']):.2f}")
                    
                    print(f"💰 Session Profit: ${self.session_profit:.2f} | Trades: {self.total_trades}")
                
                # Check stop conditions
                if self.session_profit >= 50:
                    print(f"🎯 TARGET REACHED! Profit: ${self.session_profit:.2f}")
                    break
                    
                if self.session_profit <= -100:
                    print(f"🛑 STOP LOSS HIT! Loss: ${abs(self.session_profit):.2f}")
                    break
                    
            except Exception as e:
                print(f"⚠️ Error: {e}")
                time.sleep(10)
        
        print("🏁 Trading finished")
        self.running = False
    
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
        return True

# Create bot instance
bot = TradingBot()

# ===== FLASK ROUTES =====
@app.route('/')
def dashboard():
    """Main dashboard - CRASH PROOF"""
    try:
        win_rate = (bot.wins / bot.total_trades * 100) if bot.total_trades > 0 else 0
        balance = bot.get_balance()  # This returns 10000 if API fails
        mode = "🔒 DEMO (Simulation)" if not bot.api_connected else "🔒 DEMO (Real API)"
        
        html = f"""
        <html><head><title>Deriv Bot</title><meta http-equiv="refresh" content="10">
        <style>
        body{{font-family:Arial; margin:40px; background:#f5f5f5;}}
        .container{{max-width:800px; margin:auto; background:white; padding:30px; border-radius:10px; box-shadow:0 2px 10px rgba(0,0,0,0.1);}}
        .stats{{display:grid; grid-template-columns:repeat(2,1fr); gap:20px; margin:20px 0;}}
        .stat-box{{background:#f8f9fa; padding:15px; border-radius:8px; border-left:4px solid #007bff;}}
        button{{padding:10px 20px; margin:5px; background:#007bff; color:white; border:none; border-radius:5px; cursor:pointer;}}
        .running{{color:green;}} .stopped{{color:red;}}
        .profit{{color:green; font-weight:bold;}} .loss{{color:red; font-weight:bold;}}
        </style></head>
        <body><div class="container">
        <h1>🤖 Deriv Trading Bot</h1>
        <p><strong>Status:</strong> <span class="{'running' if bot.running else 'stopped'}">
        {'🟢 RUNNING' if bot.running else '🔴 STOPPED'}</span></p>
        <p><strong>Mode:</strong> {mode}</p>
        <p><strong>API:</strong> {'✅ Connected' if bot.api_connected else '❌ Simulation Only'}</p>
        
        <div class="stats">
            <div class="stat-box"><h3>💰 Balance</h3><p>${balance:.2f}</p></div>
            <div class="stat-box"><h3>📈 Session Profit</h3><p class="{'profit' if bot.session_profit >= 0 else 'loss'}">${bot.session_profit:.2f}</p></div>
            <div class="stat-box"><h3>📊 Total Trades</h3><p>{bot.total_trades}</p></div>
            <div class="stat-box"><h3>🎯 Win Rate</h3><p>{win_rate:.1f}%</p></div>
            <div class="stat-box"><h3>✅ Wins / ❌ Losses</h3><p>{bot.wins} / {bot.losses}</p></div>
            <div class="stat-box"><h3>⏰ Last Trade</h3><p>{bot.last_trade_time.strftime('%H:%M:%S') if bot.last_trade_time else 'Never'}</p></div>
        </div>
        
        <div>
            <button onclick="window.location.href='/start'">▶️ Start Bot</button>
            <button onclick="window.location.href='/stop'">⏹️ Stop Bot</button>
            <button onclick="window.location.href='/logs'">📊 View Logs</button>
            <button onclick="window.location.href='/test-api'">🔧 Test API</button>
        </div>
        
        <p style="margin-top:30px; color:#666;">
            {'✅ Bot is trading with REAL Deriv API' if bot.api_connected else '⚠️ Bot is running in SIMULATION mode (add API token for real trading)'}
            <br>Auto-refreshes every 10 seconds.
        </p>
        </div></body></html>
        """
        return html
        
    except Exception as e:
        return f"<h1>Error</h1><p>{str(e)}</p>"

@app.route('/start')
def start_bot():
    bot.start()
    return jsonify({"status": "started", "message": "Bot started!"})

@app.route('/stop')
def stop_bot():
    bot.stop()
    return jsonify({"status": "stopped", "message": "Bot stopped!"})

@app.route('/logs')
def show_logs():
    try:
        # Simple log viewer
        logs = ["Logs will appear here when trading starts..."]
        return f"<pre>{chr(10).join(logs)}</pre>"
    except:
        return "<pre>No logs available</pre>"

@app.route('/test-api')
def test_api():
    """Test API connection"""
    if bot.test_api():
        return jsonify({"status": "connected", "message": "API is working!"})
    else:
        return jsonify({"status": "failed", "message": "API connection failed. Check token."})

# Auto-start bot
def auto_start():
    time.sleep(5)
    print("🚀 Auto-starting bot...")
    bot.start()

if __name__ == "__main__":
    if os.getenv('RENDER'):
        threading.Thread(target=auto_start, daemon=True).start()
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
