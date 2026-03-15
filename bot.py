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

last_signal = {}

def get_pairs():
    url = "https://api.binance.com/api/v3/ticker/24hr"
    data = requests.get(url).json()
    pairs = [x for x in data if "USDT" in x["symbol"]]
    pairs = sorted(pairs, key=lambda x: float(x["quoteVolume"]), reverse=True)
    return pairs[:PAIR_LIMIT]

def analyze_gpt(symbol, price, change, volume):

    prompt = f"""
You are elite crypto intraday trader.

Analyze market data:

Pair: {symbol}
Price: {price}
24h Change: {change}
Volume: {volume}

Decide:
1) Direction: LONG / SHORT / NO TRADE
2) Confidence: %
3) Entry logic short explanation

Answer format:
DIRECTION | CONFIDENCE | REASON
"""

    r = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role":"user","content":prompt}],
        temperature=0.2
    )

    return r.choices[0].message.content

def send_signal(symbol, side, entry, conf, reason):

    if side == "LONG":
        sl = entry * 0.985
        tp1 = entry * 1.02
        tp2 = entry * 1.035
        tp3 = entry * 1.06
    else:
        sl = entry * 1.015
        tp1 = entry * 0.98
        tp2 = entry * 0.965
        tp3 = entry * 0.94

    msg = f"""
🤖 AI GPT SIGNAL

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

    requests.post(SEND_URL, data={"chat_id":CHAT_ID,"text":msg})

while True:
    try:
        pairs = get_pairs()

        for p in pairs:
            symbol = p["symbol"]
            price = float(p["lastPrice"])
            change = p["priceChangePercent"]
            volume = p["quoteVolume"]

            ai = analyze_gpt(symbol, price, change, volume)

            try:
                side, conf, reason = ai.split("|")
                side = side.strip()
                conf = int(conf.strip())
                reason = reason.strip()
            except:
                continue

            now = time.time()

            if side != "NO TRADE" and conf >= CONF_FILTER:
                if symbol not in last_signal or now - last_signal[symbol] > 3600:
                    send_signal(symbol, side, price, conf, reason)
                    last_signal[symbol] = now
                    print("AI SIGNAL:", symbol)

        time.sleep(SCAN_INTERVAL)

    except Exception as e:
        print("ERR:", e)
        time.sleep(20)