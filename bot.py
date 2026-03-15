import requests
import time
import os
import math

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

SEND_URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

SCAN_INTERVAL = 25
BATCH_SIZE = 40
COOLDOWN = 1800
MIN_MOVE = 0.2
VOL_SPIKE = 1.2

last_price = {}
last_signal_time = {}
last_signal_side = {}

# ================= GET SYMBOLS =================

def get_symbols():

    url = "https://open-api.bingx.com/openApi/swap/v2/quote/contracts"

    try:
        r = requests.get(url, timeout=15)
        data = r.json()

        symbols = []

        for s in data["data"]:
            if "USDT" in s["symbol"]:
                symbols.append(s["symbol"])

        return symbols

    except:
        return []

# ================= PRICE =================

def get_price(symbol):

    url = f"https://open-api.bingx.com/openApi/swap/v2/quote/price?symbol={symbol}"

    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        return float(data["data"]["price"])
    except:
        return None

# ================= VOLUME =================

def get_volume(symbol):

    url = f"https://open-api.bingx.com/openApi/swap/v2/quote/kline?symbol={symbol}&interval=1m&limit=2"

    try:
        r = requests.get(url, timeout=10)
        data = r.json()

        v_now = float(data["data"][1]["volume"])
        v_prev = float(data["data"][0]["volume"])

        return v_now, v_prev
    except:
        return None, None

# ================= ANALYZE =================

def analyze(symbol):

    price = get_price(symbol)
    v_now, v_prev = get_volume(symbol)

    if not price or not v_now or not v_prev:
        return None

    volume_spike = v_now / v_prev

    if symbol not in last_price:
        last_price[symbol] = price
        return None

    change = (price - last_price[symbol]) / last_price[symbol] * 100
    last_price[symbol] = price

    if abs(change) < MIN_MOVE:
        return None

    if volume_spike < VOL_SPIKE:
        return None

    side = "LONG" if change > 0 else "SHORT"
    now = time.time()

    if symbol in last_signal_time:
        if now - last_signal_time[symbol] < COOLDOWN:
            return None

    if symbol in last_signal_side:
        if last_signal_side[symbol] == side:
            return None

    last_signal_time[symbol] = now
    last_signal_side[symbol] = side

    return side, price, change, volume_spike

# ================= TELEGRAM =================

def send_signal(symbol, side, entry, change, vol):

    if side == "LONG":
        sl = entry * 0.99
        tp1 = entry * 1.02
        tp2 = entry * 1.04
    else:
        sl = entry * 1.01
        tp1 = entry * 0.98
        tp2 = entry * 0.96

    msg = f"""
💀 BINGX ROLLING SNIPER

Pair : {symbol}
Side : {side}

Entry : {entry:.4f}

TP1 : {tp1:.4f}
TP2 : {tp2:.4f}
SL : {sl:.4f}

Move : {change:.2f}%
Volume Spike : {vol:.2f}x
"""

    try:
        requests.post(SEND_URL, data={"chat_id": CHAT_ID, "text": msg})
    except:
        print("telegram error")

# ================= MAIN =================

symbols = get_symbols()
total = len(symbols)

print("TOTAL SYMBOL:", total)

batch_count = math.ceil(total / BATCH_SIZE)
batch_index = 0

while True:

    start = batch_index * BATCH_SIZE
    end = start + BATCH_SIZE

    batch = symbols[start:end]

    print(f"SCAN BATCH {batch_index+1}/{batch_count}")

    for s in batch:

        result = analyze(s)

        if result:
            side, price, change, vol = result
            send_signal(s, side, price, change, vol)
            print("SIGNAL:", s)

    batch_index += 1

    if batch_index >= batch_count:
        batch_index = 0

    time.sleep(SCAN_INTERVAL)