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
PAIR_LIMIT = 35
CONF_FILTER = 75
COOLDOWN = 3600

last_signal = {}

# ================= MARKET DATA =================

def get_pairs():
    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        r = requests.get(url, timeout=10)

        if r.status_code != 200:
            print("BINANCE API ERROR")
            return []

        data = r.json()

        if not isinstance(data, list):
            print("BINANCE FORMAT ERROR")
            return []

        pairs = [
            x for x in data
            if isinstance(x, dict)
            and "USDT" in x.get("symbol", "")
            and float(x.get("quoteVolume", 0)) > 10000000
        ]

        pairs = sorted(
            pairs,
            key=lambda x: float(x.get("quoteVolume", 0)),
            reverse=True
        )

        return pairs[:PAIR_LIMIT]

    except Exception as e:
        print("PAIR ERROR:", e)
        return []

# ================= AI ANALYSIS =================

def analyze_gpt(symbol, price, change, volume):

    prompt = f"""
You are elite crypto intraday trader.

Market data:
Pair: {symbol}
Price: {price}
24h Change: {change}
Volume: {volume}

Decide best trade.

Answer STRICT format:
LONG or SHORT or NO TRADE | confidence_number | short_reason
"""

    try:
        r = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
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

    msg = f"""
🤖 AI SMART SIGNAL

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

    try:
        requests.post(SEND_URL, data={"chat_id": CHAT_ID, "text": msg})
    except:
        print("TELEGRAM ERROR")

# ================= MAIN LOOP =================

while True:
    try:
        pairs = get_pairs()

        for p in pairs:

            symbol = p["symbol"]
            price = float(p["lastPrice"])
            change = p["priceChangePercent"]
            volume = p["quoteVolume"]

            ai = analyze_gpt(symbol, price, change, volume)

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

                    print("AI SIGNAL:", symbol)

        time.sleep(SCAN_INTERVAL)

    except Exception as e:
        print("MAIN ERROR:", e)
        time.sleep(30)