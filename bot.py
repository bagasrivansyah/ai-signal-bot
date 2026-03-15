import requests
import time
import os
from openai import OpenAI

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
OPENAI_KEY = os.getenv("OPENAI_KEY")

client = OpenAI(api_key=OPENAI_KEY)

SEND_URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

SCAN_INTERVAL = 120
PAIR_LIMIT = 40
CONF_FILTER = 75
COOLDOWN = 3600

last_signal = {}

# ================= OKX MARKET DATA =================

def get_pairs():
    try:
        url = "https://www.okx.com/api/v5/market/tickers?instType=SPOT"
        r = requests.get(url, timeout=10)

        data = r.json()

        if data.get("code") != "0":
            print("OKX ERROR")
            return []

        tickers = data.get("data", [])

        usdt = [x for x in tickers if "-USDT" in x["instId"]]

        usdt = sorted(usdt, key=lambda x: float(x["volCcy24h"]), reverse=True)

        return usdt[:PAIR_LIMIT]

    except Exception as e:
        print("OKX FETCH ERROR:", e)
        return []

# ================= AI ANALYSIS =================

def analyze_ai(symbol, price, change, volume):

    prompt = f"""
You are elite crypto intraday trader.

Market:
Pair: {symbol}
Price: {price}
24h Change: {change}
Volume: {volume}

Decide trade.

Format STRICT:
LONG or SHORT or NO TRADE | confidence | reason
"""

    try:
        r = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role":"user","content":prompt}],
            temperature=0.2
        )
        return r.choices[0].message.content

    except Exception as e:
        print("GPT ERROR:", e)
        return None

# ================= TELEGRAM =================

def send_signal(symbol, side, entry, conf, reason):

    if side == "LONG":
        sl = entry * 0.985
        tp1 = entry * 1.02
        tp2 = entry * 1.04
        tp3 = entry * 1.07
    else:
        sl = entry * 1.015
        tp1 = entry * 0.98
        tp2 = entry * 0.96
        tp3 = entry * 0.93

    text = f"""
🤖 AI SIGNAL

Pair : {symbol}
Side : {side}

Entry : {entry}

SL : {sl:.4f}

TP1 : {tp1:.4f}
TP2 : {tp2:.4f}
TP3 : {tp3:.4f}

Confidence : {conf}%
Reason : {reason}
"""

    requests.post(SEND_URL, data={"chat_id":CHAT_ID,"text":text})

# ================= MAIN LOOP =================

while True:
    try:
        pairs = get_pairs()

        for p in pairs:

            symbol = p["instId"]
            price = float(p["last"])
            change = p["sodUtc0"]
            volume = p["volCcy24h"]

            ai = analyze_ai(symbol, price, change, volume)

            if not ai:
                continue

            parts = ai.split("|")

            if len(parts) < 3:
                continue

            side = parts[0].strip().upper()

            try:
                conf = int(parts[1].strip())
            except:
                continue

            reason = parts[2].strip()

            now = time.time()

            if side != "NO TRADE" and conf >= CONF_FILTER:

                if symbol not in last_signal or now - last_signal[symbol] > COOLDOWN:

                    send_signal(symbol, side, price, conf, reason)
                    last_signal[symbol] = now

                    print("AI OKX SIGNAL:", symbol)

        time.sleep(SCAN_INTERVAL)

    except Exception as e:
        print("MAIN ERROR:", e)
        time.sleep(30)