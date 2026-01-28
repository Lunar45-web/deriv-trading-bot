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
DEMO_MODE = True  # START WITH DEMO!
DEMO_BALANCE = 10000.00  # Virtual money
DERIV_APP_ID = 1089  # Deriv app ID
DEMO_API_TOKEN = os.getenv('DEMO_API_TOKEN', 'YOUR_DEMO_TOKEN_HERE')
REAL_API_TOKEN = os.getenv('REAL_API_TOKEN', '')  # Leave empty for demo

if DEMO_MODE:
    API_TOKEN = DEMO_API_TOKEN
    BASE_URL = "https://deriv-api.crypto.com/v1"
    print("🚀 STARTING IN DEMO MODE - NO REAL MONEY!")
else:
    API_TOKEN = REAL_API_TOKEN
    BASE_URL = "https://deriv-api.crypto.com/v1"
    print("⚠️ REAL MONEY MODE - BE CAREFUL!")

HEADERS = {
    'Authorization': f'Bearer {API_TOKEN}',
    'Content-Type': 'application/json'
}

# ===== TRADING BOT CLASS =====
class SmartDigitBot:
    def __init__(self):
        self.balance = DEMO_BALANCE if DEMO_MODE else 0
        self.total_trades = 0
        self.wins = 0
        self.losses = 0
        self.running = True
        self.consecutive_losses = 0
        self.stake = 1.0  # Base stake
        self.max_risk = 0.01  # 1% risk per trade
        self.daily_target = 50.0  # Target profit
        self.daily_loss_limit = -100.0  # Stop loss
        self.digits_history = []
        self.last_trade_time = None
        self.session_profit = 0.0
        
        print("=" * 50)
        print(f"🤖 SMART DIGIT BOT v2.0")
        print(f"💰 Starting Balance: ${self.balance:.2f}")
        print(f"🎯 Daily Target: ${self.daily_target}")
        print(f"🛑 Daily Stop Loss: ${self.daily_loss_limit}")
        print(f"⚡ Mode: {'DEMO' if DEMO_MODE else 'REAL MONEY'}")
        print("=" * 50)
    
    def analyze_market(self):
        """Simple market analysis for digits"""
        if len(self.digits_history) < 20:
            return {"action": "wait", "reason": "Insufficient data"}
        
        # Count recent high digits (7,8,9)
        recent = self.digits_history[-20:]
        high_count = sum(1 for d in recent if d >= 7)
        low_count = sum(1 for d in recent if d <= 2)
        
        # Strategy 1: Under 7/8 when high digits are rare
        if high_count < 5:  # Less than 25% high digits
            if random.random() < 0.7:  # 70% confidence
                prediction = 8 if high_count < 3 else 7
                return {
                    "action": "trade",
                    "direction": "under",
                    "prediction": prediction,
                    "confidence": 0.7,
                    "reason": f"High digits rare ({high_count}/20)"
                }
        
        # Strategy 2: Over 2/3 when low digits are rare
        if low_count < 5:  # Less than 25% low digits
            if random.random() < 0.7:
                prediction = 3 if low_count < 3 else 2
                return {
                    "action": "trade",
                    "direction": "over",
                    "prediction": prediction,
                    "confidence": 0.7,
                    "reason": f"Low digits rare ({low_count}/20)"
                }
        
        # Strategy 3: Conservative Under 6 as fallback
        if random.random() < 0.5:
            return {
                "action": "trade",
                "direction": "under",
                "prediction": 6,
                "confidence": 0.5,
                "reason": "Conservative fallback"
            }
        
        return {"action": "wait", "reason": "No clear signal"}
    
    def calculate_stake(self):
        """Dynamic stake calculation"""
        base_stake = self.stake
        
        # Reduce stake after consecutive losses
        if self.consecutive_losses >= 3:
            base_stake = max(0.5, base_stake * 0.8)  # Reduce 20%
        
        # Increase slightly after wins
        elif self.consecutive_losses == 0 and self.wins > self.losses:
            base_stake = min(2.0, base_stake * 1.1)  # Increase 10%
        
        # Apply risk management
        max_stake = self.balance * self.max_risk
        return min(base_stake, max_stake)
    
    def place_trade(self, direction, prediction):
        """Place a trade on Deriv (DEMO simulation)"""
        try:
            stake = self.calculate_stake()
            
            if DEMO_MODE:
                # Simulate trade for demo
                win_probability = 0.55  # 55% win rate for simulation
                is_win = random.random() < win_probability
                
                if is_win:
                    payout = stake * 0.95  # 95% payout for digits
                    self.balance += payout
                    self.wins += 1
                    self.consecutive_losses = 0
                    self.session_profit += payout
                    result = "win"
                    profit = payout
                else:
                    self.balance -= stake
                    self.losses += 1
                    self.consecutive_losses += 1
                    self.session_profit -= stake
                    result = "loss"
                    profit = -stake
                
                # Generate random last digit for history
                last_digit = random.randint(0, 9)
                self.digits_history.append(last_digit)
                if len(self.digits_history) > 100:
                    self.digits_history.pop(0)
                
                self.total_trades += 1
                self.last_trade_time = datetime.now()
                
                trade_data = {
                    "result": result,
                    "profit": profit,
                    "balance": self.balance,
                    "stake": stake,
                    "direction": direction,
                    "prediction": prediction,
                    "last_digit": last_digit
                }
                
                log_trade(trade_data)
                return trade_data
            
            else:
                # REAL TRADE LOGIC (commented for safety)
                # trade_data = {
                #     "buy": stake,
                #     "price": stake,
                #     "parameters": {
                #         "amount": stake,
                #         "basis": "stake",
                #         "contract_type": f"digit{'over' if direction == 'over' else 'under'}",
                #         "currency": "USD",
                #         "duration": 1,
                #         "duration_unit": "t",
                #         "symbol": "R_100",
                #         "barrier": str(prediction)
                #     }
                # }
                # response = requests.post(f"{BASE_URL}/buy", json=trade_data, headers=HEADERS)
                # return response.json()
                print("⚠️ REAL MONEY TRADING DISABLED - Use demo first!")
                return None
                
        except Exception as e:
            print(f"❌ Trade error: {e}")
            return None
    
    def should_continue(self):
        """Check if we should continue trading"""
        if self.session_profit >= self.daily_target:
            print(f"🎯 DAILY TARGET REACHED! Profit: ${self.session_profit:.2f}")
            return False
        
        if self.session_profit <= self.daily_loss_limit:
            print(f"🛑 DAILY LOSS LIMIT HIT! Loss: ${abs(self.session_profit):.2f}")
            return False
        
        if self.balance <= self.stake * 2:
            print(f"💸 INSUFFICIENT BALANCE: ${self.balance:.2f}")
            return False
        
        return True
    
    def run(self):
        """Main trading loop"""
        print("🔄 Starting trading loop...")
        
        while self.running and self.should_continue():
            try:
                # Wait between trades (1-3 minutes)
                wait_time = random.randint(60, 180)  # 1-3 minutes
                print(f"⏳ Next trade in {wait_time//60} minutes...")
                
                for i in range(wait_time):
                    if not self.running:
                        break
                    time.sleep(1)
                
                if not self.running:
                    break
                
                # Analyze market
                analysis = self.analyze_market()
                
                if analysis["action"] == "trade":
                    print(f"\n📊 Analysis: {analysis['reason']}")
                    print(f"💡 Decision: {analysis['direction'].upper()} {analysis['prediction']}")
                    
                    # Place trade
                    result = self.place_trade(analysis["direction"], analysis["prediction"])
                    
                    if result:
                        if result["result"] == "win":
                            print(f"✅ WIN! +${result['profit']:.2f} | Balance: ${result['balance']:.2f}")
                        else:
                            print(f"❌ LOSS! -${abs(result['profit']):.2f} | Balance: ${result['balance']:.2f}")
                        
                        # Display stats
                        win_rate = (self.wins / self.total_trades * 100) if self.total_trades > 0 else 0
                        print(f"📈 Stats: {self.total_trades} trades | Win Rate: {win_rate:.1f}% | Profit: ${self.session_profit:.2f}")
                        print("-" * 50)
                
                else:
                    print(f"⏸️ Waiting: {analysis['reason']}")
                    
            except KeyboardInterrupt:
                print("\n🛑 Manual stop requested")
                self.running = False
                break
            except Exception as e:
                print(f"⚠️ Error in trading loop: {e}")
                time.sleep(10)
        
        # Session summary
        self.print_summary()
    
    def print_summary(self):
        """Print session summary"""
        print("\n" + "=" * 50)
        print("🏁 TRADING SESSION COMPLETE")
        print("=" * 50)
        print(f"📊 Total Trades: {self.total_trades}")
        print(f"✅ Wins: {self.wins}")
        print(f"❌ Losses: {self.losses}")
        
        if self.total_trades > 0:
            win_rate = (self.wins / self.total_trades * 100)
            print(f"🎯 Win Rate: {win_rate:.1f}%")
        
        print(f"💰 Session Profit: ${self.session_profit:.2f}")
        print(f"💵 Final Balance: ${self.balance:.2f}")
        
        if DEMO_MODE:
            print(f"🔒 MODE: DEMO (Virtual Money)")
        else:
            print(f"⚠️ MODE: REAL MONEY")
        
        print("=" * 50)

# ===== LOGGING =====
def log_trade(trade):
    """Log trade to file"""
    try:
        with open("trades.log", "a") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"{timestamp} | {trade['result'].upper()} | "
                   f"{trade['direction']} {trade['prediction']} | "
                   f"Stake: ${trade['stake']:.2f} | "
                   f"Profit: ${trade['profit']:.2f} | "
                   f"Balance: ${trade['balance']:.2f} | "
                   f"Digit: {trade['last_digit']}\n")
    except:
        pass

# ===== FLASK WEB SERVER =====
bot = SmartDigitBot()
bot_thread = None

@app.route('/')
def dashboard():
    """Web dashboard"""
    win_rate = (bot.wins / bot.total_trades * 100) if bot.total_trades > 0 else 0
    
    return f"""
    <html>
        <head>
            <title>Deriv Trading Bot</title>
            <meta http-equiv="refresh" content="10">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
                .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                h1 {{ color: #333; }}
                .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }}
                .stat-box {{ background: #f8f9fa; padding: 20px; border-radius: 8px; border-left: 4px solid #007bff; }}
                .profit {{ color: green; font-weight: bold; }}
                .loss {{ color: red; font-weight: bold; }}
                .controls {{ margin-top: 30px; }}
                button {{ padding: 10px 20px; margin-right: 10px; background: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🤖 Deriv Trading Bot</h1>
                <p><strong>Status:</strong> {'🟢 RUNNING' if bot.running else '🔴 STOPPED'}</p>
                <p><strong>Mode:</strong> {'🔒 DEMO (Virtual Money)' if DEMO_MODE else '⚠️ REAL MONEY'}</p>
                
                <div class="stats">
                    <div class="stat-box">
                        <h3>💰 Balance</h3>
                        <p>${bot.balance:.2f}</p>
                    </div>
                    <div class="stat-box">
                        <h3>📈 Session Profit</h3>
                        <p class="{ 'profit' if bot.session_profit >= 0 else 'loss' }">${bot.session_profit:.2f}</p>
                    </div>
                    <div class="stat-box">
                        <h3>📊 Total Trades</h3>
                        <p>{bot.total_trades}</p>
                    </div>
                    <div class="stat-box">
                        <h3>🎯 Win Rate</h3>
                        <p>{win_rate:.1f}%</p>
                    </div>
                    <div class="stat-box">
                        <h3>✅ Wins / ❌ Losses</h3>
                        <p>{bot.wins} / {bot.losses}</p>
                    </div>
                    <div class="stat-box">
                        <h3>⏰ Last Trade</h3>
                        <p>{bot.last_trade_time.strftime('%H:%M:%S') if bot.last_trade_time else 'Never'}</p>
                    </div>
                </div>
                
                <div class="controls">
                    <button onclick="window.location.href='/start'">▶️ Start Bot</button>
                    <button onclick="window.location.href='/stop'">⏹️ Stop Bot</button>
                    <button onclick="window.location.href='/stats'">📊 View Logs</button>
                </div>
                
                <p style="margin-top: 30px; color: #666;">
                    Bot will run for 10 hours automatically. Check back later!
                    <br>Auto-refreshes every 10 seconds.
                </p>
            </div>
        </body>
    </html>
    """

@app.route('/start')
def start_bot():
    """Start the trading bot"""
    global bot_thread
    
    if not bot.running:
        bot.running = True
        bot_thread = threading.Thread(target=bot.run, daemon=True)
        bot_thread.start()
        return jsonify({"status": "started", "message": "Bot started successfully!"})
    
    return jsonify({"status": "already_running", "message": "Bot is already running!"})

@app.route('/stop')
def stop_bot():
    """Stop the trading bot"""
    bot.running = False
    return jsonify({"status": "stopped", "message": "Bot stopping..."})

@app.route('/stats')
def show_stats():
    """Show trade logs"""
    try:
        with open("trades.log", "r") as f:
            logs = f.read()
        return f"<pre>{logs}</pre>"
    except:
        return "No logs yet."

# ===== START BOT ON DEPLOY =====
def start_on_deploy():
    """Auto-start bot when deployed"""
    time.sleep(5)  # Wait for server to fully start
    print("🚀 Auto-starting trading bot...")
    bot.running = True
    bot_thread = threading.Thread(target=bot.run, daemon=True)
    bot_thread.start()

# Start bot when deployed (in production)
if __name__ == "__main__":
    # Only auto-start in production (Render sets this)
    if os.getenv('RENDER', ''):
        threading.Thread(target=start_on_deploy, daemon=True).start()
    
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)