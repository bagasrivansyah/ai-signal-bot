import requests
import time
import os

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
ALTFINS_KEY = os.getenv("ALTFINS_KEY")

SEND_URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

SCAN_INTERVAL = 300
CONF_FILTER = 75
COOLDOWN = 3600

headers = {
    "Authorization": f"Bearer {ALTFINS_KEY}"
}

last_signal = {}

# ================= GET ALL COINS =================

def get_market():

    url = "https://platform.altfins.com/api/v1/market/coins"

    try:
        r = requests.get(url, headers=headers, timeout=15)
        data = r.json()
        return data
    except:
        return []

# ================= ANALYZE =================

def analyze(coin):

    try:
        symbol = coin["symbol"]
        trend = float(coin["trendStrength"])
        price = float(coin["price"])
    except:
        return None

    if trend > 70:
        side = "LONG"
        conf = min(95, trend)

    elif trend < 30:
        side = "SHORT"
        conf = min(95, 100 - trend)

    else:
        return None

    return symbol, side, conf, price, trend

# ================= TELEGRAM =================

def send_signal(symbol, side, entry, conf, trend):

    if side == "LONG":
        sl = entry * 0.985
        tp1 = entry * 1.025
        tp2 = entry * 1.05
        tp3 = entry * 1.08
    else:
        sl = entry * 1.015
        tp1 = entry * 0.975
        tp2 = entry * 0.95
        tp3 = entry * 0.92

    msg = f"""
🚨 ALTFINS SNIPER SIGNAL

Pair : {symbol}USDT
Side : {side}

Entry : {entry}

SL : {sl:.4f}

TP1 : {tp1:.4f}
TP2 : {tp2:.4f}
TP3 : {tp3:.4f}

Trend Score : {trend}
Confidence : {conf}%
"""

    requests.post(SEND_URL, data={"chat_id": CHAT_ID, "text": msg})

# ================= MAIN LOOP =================

while True:

    coins = get_market()

    print("SCAN COINS:", len(coins))

    for c in coins:

        result = analyze(c)

        if not result:
            continue

        symbol, side, conf, price, trend = result

        now = time.time()

        if conf >= CONF_FILTER:

            if symbol not in last_signal or now - last_signal[symbol] > COOLDOWN:

                send_signal(symbol, side, price, conf, trend)
                last_signal[symbol] = now

                print("SIGNAL:", symbol)

    time.sleep(SCAN_INTERVAL)