import asyncio
import os
import threading
from flask import Flask
from deriv_api import DerivAPI
from deriv_api.errors import APIError

# --- CONFIGURATION ---
# We try to get the token from Render Environment variables first.
# If not found, we fall back to your demo token.
API_TOKEN = os.getenv('DERIV_API_TOKEN', 's4TVgxiEc36iXSM') 
APP_ID = 1089
SYMBOL = 'R_100'  # Volatility 100 (1s) - Very fast market
BASE_STAKE = 0.35
MARTINGALE_MULTIPLIER = 2.1  # Slightly over 2x to cover potential spread/losses
MAX_LOSS_STREAK = 4

# --- GLOBAL VARIABLES ---
tick_history = []
current_loss_streak = 0
is_trading = False

# --- FLASK SERVER (TO KEEP RENDER HAPPY) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Deriv Sniper Bot is Running..."

def run_web_server():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

# --- TRADING BOT LOGIC ---
async def execute_trade(api, contract_type, barrier, prediction_name):
    global current_loss_streak, is_trading

    is_trading = True
    
    # Calculate Stake
    stake = BASE_STAKE
    if current_loss_streak > 0:
        stake = round(BASE_STAKE * (MARTINGALE_MULTIPLIER ** current_loss_streak), 2)

    print(f"\n>>> SNIPER SHOT: {prediction_name} | Stake: ${stake} | Barrier: {barrier}")

    try:
        # Buy Contract
        proposal = await api.buy({
            "buy": 1,
            "price": stake,
            "parameters": {
                "contract_type": contract_type,
                "symbol": SYMBOL,
                "duration": 1,
                "duration_unit": "t",
                "basis": "stake",
                "currency": "USD",
                "barrier": str(barrier)
            }
        })

        contract_id = proposal['buy']['contract_id']
        
        # Wait for result
        # We perform a simple loop to check status
        while True:
            history = await api.profit_table({"description": 1, "limit": 1})
            # Check if our specific contract is in the latest history
            if history['profit_table']['transactions']:
                latest = history['profit_table']['transactions'][0]
                if latest['contract_id'] == contract_id:
                    # Trade Finished
                    profit = float(latest['sell_price']) - float(latest['buy_price'])
                    
                    if profit > 0:
                        print(f"✅ WIN! Profit: ${profit}")
                        current_loss_streak = 0
                    else:
                        print(f"❌ LOSS. Loss: ${stake}")
                        current_loss_streak += 1
                        if current_loss_streak >= MAX_LOSS_STREAK:
                            print("⚠️ Max Loss Streak Reached. Resetting Stake.")
                            current_loss_streak = 0
                    break
            
            await asyncio.sleep(1)

    except Exception as e:
        print(f"Error executing trade: {e}")
    
    is_trading = False

async def run_bot():
    global tick_history, is_trading

    print("Connecting to Deriv API...")
    api = DerivAPI(app_id=APP_ID)
    
    try:
        authorize = await api.authorize(API_TOKEN)
        print(f"Logged in as: {authorize['authorize']['email']}")
    except APIError as e:
        print(f"Login Failed: {e}")
        return

    # Subscribe to Ticks
    source_ticks = await api.subscribe({'ticks': SYMBOL})
    
    print(f"Subscribed to {SYMBOL}. Waiting for patterns...")

    # Process stream
    async for tick in source_ticks:
        # 1. Update History
        quote = tick['tick']['quote']
        last_digit = int(str(quote)[-1])
        tick_history.append(last_digit)
        
        if len(tick_history) > 10:
            tick_history.pop(0)
            
        print(f"Digit: {last_digit} | Hist: {tick_history[-5:]}", end="\r")

        # 2. Skip if already trading or not enough data
        if is_trading or len(tick_history) < 5:
            continue

        # --- STRATEGY: UNDER 7 ---
        # Trigger: If last 3 digits are all >= 7 (Trend High) -> Bet Reversal (Under 7)
        # We bet that the market cannot sustain high digits forever.
        if all(d >= 7 for d in tick_history[-3:]):
            print("\nTrigger: High Cluster Detected (>=7). Firing Under 7...")
            asyncio.create_task(execute_trade(api, "DIGITUNDER", 7, "Under 7"))
            continue

        # --- STRATEGY: OVER 2 ---
        # Trigger: If last 3 digits are all <= 2 (Trend Low) -> Bet Reversal (Over 2)
        # We bet that the market cannot sustain low digits forever.
        if all(d <= 2 for d in tick_history[-3:]):
            print("\nTrigger: Low Cluster Detected (<=2). Firing Over 2...")
            # Note: For 'Over 2', we typically use DIGITOVER with barrier 2
            asyncio.create_task(execute_trade(api, "DIGITOVER", 2, "Over 2"))
            continue

if __name__ == "__main__":
    # Start the Dummy Web Server in a separate thread
    t = threading.Thread(target=run_web_server)
    t.start()

    # Start the Trading Bot in the main Asyncio loop
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_bot())
