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
API_TOKEN = os.getenv('DEMO_API_TOKEN', 'demo_token')
HEADERS = {'Authorization': f'Bearer {API_TOKEN}'}

# ===== GLOBAL BOT INSTANCE =====
bot_instance = None

# ===== TRADING BOT CLASS =====
class SmartDigitBot:
    def __init__(self):
        global bot_instance
        bot_instance = self
        self.balance = DEMO_BALANCE
        self.total_trades = 0
        self.wins = 0
        self.losses = 0
        self.running = False  # Start as False
        self.consecutive_losses = 0
        self.stake = 1.0
        self.session_profit = 0.0
        self.last_trade_time = None
        self.digits_history = []
        
        print("=" * 50)
        print(f"🤖 SMART DIGIT BOT v2.0")
        print(f"💰 Starting Balance: ${self.balance:.2f}")
        print("=" * 50)
    
    def analyze_market(self):
        """Simple market analysis"""
        if len(self.digits_history) < 10:
            # Initialize with some random digits
            self.digits_history = [random.randint(0,9) for _ in range(20)]
        
        recent = self.digits_history[-20:]
        high_count = sum(1 for d in recent if d >= 7)
        
        if high_count < 5:
            return {"action": "trade", "direction": "under", "prediction": 7}
        else:
            return {"action": "trade", "direction": "over", "prediction": 3}
    
    def simulate_trade(self):
        """Simulate a demo trade"""
        stake = min(self.stake, self.balance * 0.01)
        
        # 55% win probability
        is_win = random.random() < 0.55
        
        if is_win:
            profit = stake * 0.95
            self.balance += profit
            self.wins += 1
            self.consecutive_losses = 0
            self.session_profit += profit
            result = "win"
        else:
            profit = -stake
            self.balance -= stake
            self.losses += 1
            self.consecutive_losses += 1
            self.session_profit -= stake
            result = "loss"
        
        # Update digit history
        last_digit = random.randint(0, 9)
        self.digits_history.append(last_digit)
        if len(self.digits_history) > 100:
            self.digits_history.pop(0)
        
        self.total_trades += 1
        self.last_trade_time = datetime.now()
        
        return {
            "result": result,
            "profit": profit,
            "balance": self.balance,
            "stake": stake,
            "last_digit": last_digit
        }
    
    def trading_loop(self):
        """Main trading loop - runs in separate thread"""
        print("🔄 Trading loop STARTED!")
        
        trade_count = 0
        while self.running and trade_count < 500:  # Safety limit
            try:
                # Wait 60-120 seconds between trades
                wait_time = random.randint(60, 120)
                print(f"⏳ Waiting {wait_time} seconds for next trade...")
                
                for _ in range(wait_time):
                    if not self.running:
                        break
                    time.sleep(1)
                
                if not self.running:
                    break
                
                # Make trade decision
                analysis = self.analyze_market()
                
                if analysis["action"] == "trade":
                    print(f"📊 Making trade: {analysis['direction']} {analysis['prediction']}")
                    
                    # Execute trade
                    trade_result = self.simulate_trade()
                    
                    # Log result
                    if trade_result["result"] == "win":
                        print(f"✅ WIN! +${trade_result['profit']:.2f} | Balance: ${trade_result['balance']:.2f}")
                    else:
                        print(f"❌ LOSS! -${abs(trade_result['profit']):.2f} | Balance: ${trade_result['balance']:.2f}")
                    
                    trade_count += 1
                    
                    # Log to file
                    self.log_trade(trade_result, analysis)
                    
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
        
        print(f"🏁 Trading loop finished. Total trades: {trade_count}")
        self.running = False
    
    def log_trade(self, trade, analysis):
        """Log trade to console and file"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = (f"{timestamp} | {trade['result'].upper()} | "
                    f"{analysis['direction']} {analysis['prediction']} | "
                    f"Profit: ${trade['profit']:.2f} | "
                    f"Balance: ${trade['balance']:.2f} | "
                    f"Digit: {trade['last_digit']}")
        
        print(f"📝 {log_entry}")
        
        # Also write to file
        try:
            with open("trades.log", "a") as f:
                f.write(log_entry + "\n")
        except:
            pass
    
    def start(self):
        """Start the trading bot"""
        if not self.running:
            self.running = True
            # Start trading loop in separate thread
            thread = threading.Thread(target=self.trading_loop, daemon=True)
            thread.start()
            print("🚀 Bot started successfully!")
            return True
        return False
    
    def stop(self):
        """Stop the trading bot"""
        self.running = False
        print("🛑 Bot stopped")
        return True

# ===== CREATE BOT INSTANCE =====
bot = SmartDigitBot()

# ===== FLASK ROUTES =====
@app.route('/')
def dashboard():
    """Web dashboard"""
    win_rate = (bot.wins / bot.total_trades * 100) if bot.total_trades > 0 else 0
    
    html = f"""
    <html>
        <head>
            <title>Deriv Trading Bot</title>
            <meta http-equiv="refresh" content="10">
            <style>
                body {{ font-family: Arial; margin: 40px; background: #f5f5f5; }}
                .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                h1 {{ color: #333; }}
                .stats {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; margin: 20px 0; }}
                .stat-box {{ background: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 4px solid #007bff; }}
                .profit {{ color: green; font-weight: bold; }}
                .loss {{ color: red; font-weight: bold; }}
                button {{ padding: 10px 20px; margin: 5px; background: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; }}
                .running {{ color: green; }}
                .stopped {{ color: red; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🤖 Deriv Trading Bot</h1>
                <p><strong>Status:</strong> <span class="{'running' if bot.running else 'stopped'}">{'🟢 RUNNING' if bot.running else '🔴 STOPPED'}</span></p>
                <p><strong>Mode:</strong> {'🔒 DEMO (Virtual Money)' if DEMO_MODE else '⚠️ REAL MONEY'}</p>
                
                <div class="stats">
                    <div class="stat-box"><h3>💰 Balance</h3><p>${bot.balance:.2f}</p></div>
                    <div class="stat-box"><h3>📈 Session Profit</h3><p class="{ 'profit' if bot.session_profit >= 0 else 'loss' }">${bot.session_profit:.2f}</p></div>
                    <div class="stat-box"><h3>📊 Total Trades</h3><p>{bot.total_trades}</p></div>
                    <div class="stat-box"><h3>🎯 Win Rate</h3><p>{win_rate:.1f}%</p></div>
                    <div class="stat-box"><h3>✅ Wins / ❌ Losses</h3><p>{bot.wins} / {bot.losses}</p></div>
                    <div class="stat-box"><h3>⏰ Last Trade</h3><p>{bot.last_trade_time.strftime('%H:%M:%S') if bot.last_trade_time else 'Never'}</p></div>
                </div>
                
                <div style="margin-top: 30px;">
                    <button onclick="window.location.href='/start'">▶️ Start Bot</button>
                    <button onclick="window.location.href='/stop'">⏹️ Stop Bot</button>
                    <button onclick="window.location.href='/logs'">📊 View Logs</button>
                    <button onclick="window.location.href='/force-trade'">⚡ Force Test Trade</button>
                </div>
                
                <p style="margin-top: 30px; color: #666;">
                    Bot will run automatically. Check back in 10 hours!
                    <br>Auto-refreshes every 10 seconds.
                </p>
            </div>
        </body>
    </html>
    """
    return html

@app.route('/start')
def start_bot():
    """Start the trading bot"""
    if bot.start():
        return jsonify({"status": "started", "message": "Bot started successfully!"})
    else:
        return jsonify({"status": "already_running", "message": "Bot is already running!"})

@app.route('/stop')
def stop_bot():
    """Stop the trading bot"""
    bot.stop()
    return jsonify({"status": "stopped", "message": "Bot stopped!"})

@app.route('/logs')
def show_logs():
    """Show trade logs"""
    try:
        with open("trades.log", "r") as f:
            logs = f.read()
        return f"<pre>{logs if logs else 'No logs yet.'}</pre>"
    except:
        return "<pre>No logs yet.</pre>"

@app.route('/force-trade')
def force_trade():
    """Force a test trade (for debugging)"""
    analysis = bot.analyze_market()
    trade_result = bot.simulate_trade()
    bot.log_trade(trade_result, analysis)
    
    return jsonify({
        "status": "trade_executed",
        "result": trade_result["result"],
        "profit": trade_result["profit"],
        "balance": trade_result["balance"]
    })

# ===== AUTO-START ON DEPLOY =====
def auto_start_bot():
    """Auto-start bot when deployed (with delay)"""
    time.sleep(10)  # Wait for server to fully start
    print("🚀 AUTO-STARTING BOT...")
    bot.start()

# Start bot automatically when deployed
if __name__ == "__main__":
    # Auto-start in production
    if os.getenv('RENDER'):
        print("🌐 Running on Render - auto-starting bot...")
        threading.Thread(target=auto_start_bot, daemon=True).start()
    
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
