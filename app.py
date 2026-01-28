import os
import time
import json
import requests
from datetime import datetime
from flask import Flask, jsonify
import threading
import random

app = Flask(__name__)

# ===== CONFIGURATION =====
DEMO_MODE = True
DEMO_BALANCE = 10000.00
API_TOKEN = os.getenv('DEMO_API_TOKEN', '')  # GET FROM RENDER ENV
BASE_URL = "https://deriv-api.crypto.com/v1"

if not API_TOKEN:
    print("❌ ERROR: No API token found!")
    print("✅ Add DEMO_API_TOKEN to Render environment variables")
    exit(1)

HEADERS = {
    'Authorization': f'Bearer {API_TOKEN}',
    'Content-Type': 'application/json'
}

# ===== GLOBAL BOT INSTANCE =====
bot_instance = None

# ===== REAL DERIV TRADING BOT =====
class RealDerivBot:
    def __init__(self):
        global bot_instance
        bot_instance = self
        self.running = False
        self.total_trades = 0
        self.wins = 0
        self.losses = 0
        self.session_profit = 0.0
        self.last_trade_time = None
        self.stake = 1.0
        
        # Test API connection
        self.test_connection()
    
    def test_connection(self):
        """Test if API token works"""
        print("🔌 Testing Deriv API connection...")
        try:
            response = requests.get(
                f"{BASE_URL}/balance",
                headers=HEADERS
            )
            
            if response.status_code == 200:
                data = response.json()
                balance = data.get('balance', {}).get('balance', 0)
                print(f"✅ API Connected! Demo Balance: ${balance}")
                return True
            else:
                print(f"❌ API Error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False
    
    def get_balance(self):
        """Get real balance from Deriv"""
        try:
            response = requests.get(
                f"{BASE_URL}/balance",
                headers=HEADERS
            )
            if response.status_code == 200:
                data = response.json()
                return data.get('balance', {}).get('balance', 0)
        except:
            return DEMO_BALANCE  # Fallback
    
    def place_real_trade(self, direction, prediction):
        """Place REAL trade on Deriv"""
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
            
            print(f"📤 Placing REAL trade: {direction} {prediction} with ${self.stake}")
            
            response = requests.post(
                f"{BASE_URL}/buy",
                json=trade_data,
                headers=HEADERS
            )
            
            if response.status_code == 200:
                result = response.json()
                contract_id = result.get("buy", {}).get("contract_id")
                
                print(f"✅ Trade placed! Contract ID: {contract_id}")
                
                # Wait for contract to settle
                time.sleep(2)
                
                # Check result
                check_response = requests.get(
                    f"{BASE_URL}/proposal_open_contract",
                    params={'contract_id': contract_id},
                    headers=HEADERS
                )
                
                if check_response.status_code == 200:
                    contract_data = check_response.json()
                    profit = contract_data.get("proposal_open_contract", {}).get("profit", 0)
                    payout = contract_data.get("proposal_open_contract", {}).get("payout", 0)
                    
                    # Get last digit from market (you'd need to parse tick history)
                    last_digit = random.randint(0, 9)  # Placeholder
                    
                    trade_result = {
                        "success": True,
                        "result": "win" if profit > 0 else "loss",
                        "profit": profit,
                        "payout": payout,
                        "contract_id": contract_id,
                        "last_digit": last_digit
                    }
                    
                    print(f"💰 Trade result: {trade_result['result'].upper()} | Profit: ${profit:.2f}")
                    return trade_result
            
            print(f"❌ Trade failed: {response.text}")
            return {"success": False, "error": response.text}
            
        except Exception as e:
            print(f"❌ Trade error: {e}")
            return {"success": False, "error": str(e)}
    
    def analyze_market(self):
        """Simple market analysis for digits"""
        # In real bot, you'd analyze actual tick data
        # For now, random decision
        decisions = [
            {"action": "trade", "direction": "under", "prediction": 7, "reason": "Random Under 7"},
            {"action": "trade", "direction": "under", "prediction": 8, "reason": "Random Under 8"},
            {"action": "trade", "direction": "over", "prediction": 2, "reason": "Random Over 2"},
            {"action": "trade", "direction": "over", "prediction": 3, "reason": "Random Over 3"},
            {"action": "wait", "reason": "Market analysis"}
        ]
        return random.choice(decisions)
    
    def trading_loop(self):
        """Main trading loop"""
        print("🔄 REAL Trading loop STARTED!")
        
        while self.running and self.total_trades < 100:  # Safety limit
            try:
                # Wait 2-5 minutes between trades
                wait_time = random.randint(120, 300)
                print(f"⏳ Waiting {wait_time//60} minutes for next trade...")
                
                for _ in range(wait_time):
                    if not self.running:
                        break
                    time.sleep(1)
                
                if not self.running:
                    break
                
                # Make trade decision
                analysis = self.analyze_market()
                
                if analysis["action"] == "trade":
                    print(f"📊 Decision: {analysis['direction'].upper()} {analysis['prediction']} - {analysis['reason']}")
                    
                    # Place REAL trade
                    trade_result = self.place_real_trade(analysis["direction"], analysis["prediction"])
                    
                    if trade_result["success"]:
                        self.total_trades += 1
                        self.session_profit += trade_result["profit"]
                        self.last_trade_time = datetime.now()
                        
                        if trade_result["result"] == "win":
                            self.wins += 1
                            print(f"✅ REAL WIN! Profit: ${trade_result['profit']:.2f}")
                        else:
                            self.losses += 1
                            print(f"❌ REAL LOSS! Loss: ${abs(trade_result['profit']):.2f}")
                        
                        # Get updated balance
                        current_balance = self.get_balance()
                        print(f"💰 Current Balance: ${current_balance:.2f} | Session Profit: ${self.session_profit:.2f}")
                        
                        # Log trade
                        self.log_trade(trade_result, analysis)
                    
                    else:
                        print(f"⚠️ Trade failed: {trade_result.get('error', 'Unknown error')}")
                
                else:
                    print(f"⏸️ Waiting: {analysis['reason']}")
                
                # Check stop conditions
                if self.session_profit >= 50:
                    print(f"🎯 Target reached! Profit: ${self.session_profit:.2f}")
                    break
                    
                if self.session_profit <= -100:
                    print(f"🛑 Stop loss hit! Loss: ${abs(self.session_profit):.2f}")
                    break
                    
            except Exception as e:
                print(f"⚠️ Error in trading loop: {e}")
                time.sleep(10)
        
        print(f"🏁 Trading finished. Total trades: {self.total_trades}")
        self.running = False
    
    def log_trade(self, trade, analysis):
        """Log trade"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = (f"{timestamp} | {trade['result'].upper()} | "
                    f"{analysis['direction']} {analysis['prediction']} | "
                    f"Profit: ${trade['profit']:.2f} | "
                    f"Session Profit: ${self.session_profit:.2f}")
        
        print(f"📝 {log_entry}")
        
        try:
            with open("trades.log", "a") as f:
                f.write(log_entry + "\n")
        except:
            pass
    
    def start(self):
        """Start the bot"""
        if not self.running:
            self.running = True
            thread = threading.Thread(target=self.trading_loop, daemon=True)
            thread.start()
            print("🚀 REAL Bot started successfully!")
            return True
        return False
    
    def stop(self):
        """Stop the bot"""
        self.running = False
        print("🛑 Bot stopped")
        return True

# ===== CREATE BOT =====
bot = RealDerivBot()

# ===== FLASK ROUTES (Same as before, shortened for space) =====
@app.route('/')
def dashboard():
    win_rate = (bot.wins / bot.total_trades * 100) if bot.total_trades > 0 else 0
    current_balance = bot.get_balance()
    
    return f"""
    <html><head><title>Deriv Trading Bot</title><meta http-equiv="refresh" content="10">
    <style>body{{font-family:Arial; margin:40px; background:#f5f5f5;}}
    .container{{max-width:800px; margin:auto; background:white; padding:30px; border-radius:10px;}}
    .stats{{display:grid; grid-template-columns:repeat(2,1fr); gap:20px; margin:20px 0;}}
    .stat-box{{background:#f8f9fa; padding:15px; border-radius:8px; border-left:4px solid #007bff;}}
    button{{padding:10px 20px; margin:5px; background:#007bff; color:white; border:none; border-radius:5px; cursor:pointer;}}
    </style></head>
    <body><div class="container">
    <h1>🤖 REAL Deriv Trading Bot</h1>
    <p><strong>Status:</strong> {'🟢 RUNNING' if bot.running else '🔴 STOPPED'}</p>
    <p><strong>Mode:</strong> {'🔒 DEMO' if DEMO_MODE else '⚠️ REAL MONEY'}</p>
    <div class="stats">
        <div class="stat-box"><h3>💰 Real Balance</h3><p>${current_balance:.2f}</p></div>
        <div class="stat-box"><h3>📈 Session Profit</h3><p>${bot.session_profit:.2f}</p></div>
        <div class="stat-box"><h3>📊 Total Trades</h3><p>{bot.total_trades}</p></div>
        <div class="stat-box"><h3>🎯 Win Rate</h3><p>{win_rate:.1f}%</p></div>
        <div class="stat-box"><h3>✅ Wins / ❌ Losses</h3><p>{bot.wins} / {bot.losses}</p></div>
        <div class="stat-box"><h3>⏰ Last Trade</h3><p>{bot.last_trade_time.strftime('%H:%M:%S') if bot.last_trade_time else 'Never'}</p></div>
    </div>
    <div><button onclick="window.location.href='/start'">▶️ Start Bot</button>
    <button onclick="window.location.href='/stop'">⏹️ Stop Bot</button>
    <button onclick="window.location.href='/logs'">📊 View Logs</button></div>
    <p style='margin-top:30px; color:#666;'>Bot places REAL trades on Deriv. Check your Deriv account!</p>
    </div></body></html>
    """

@app.route('/start')
def start_bot():
    if bot.start():
        return jsonify({"status": "started", "message": "Real bot started!"})
    return jsonify({"status": "already_running", "message": "Bot already running!"})

@app.route('/stop')
def stop_bot():
    bot.stop()
    return jsonify({"status": "stopped", "message": "Bot stopped!"})

@app.route('/logs')
def show_logs():
    try:
        with open("trades.log", "r") as f:
            logs = f.read()
        return f"<pre>{logs if logs else 'No logs yet.'}</pre>"
    except:
        return "<pre>No logs yet.</pre>"

# Auto-start
def auto_start():
    time.sleep(10)
    print("🚀 Auto-starting REAL bot...")
    bot.start()

if __name__ == "__main__":
    if os.getenv('RENDER'):
        threading.Thread(target=auto_start, daemon=True).start()
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
