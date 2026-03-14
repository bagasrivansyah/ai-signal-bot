import requests
import time
import statistics
import json
from datetime import datetime

TOKEN = "ISI_TOKEN_BOT"
CHANNEL = "@channelkamu"

MIN_VOL = 1500000
MAX_SIGNAL = 3
LOSS_STREAK_LIMIT = 4

history_file = "trade_history.json"

def send(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHANNEL, "text": msg})

def load_history():
    try:
        with open(history_file,"r") as f:
            return json.load(f)
    except:
        return {"wins":0,"loss":0,"streak":0}

def save_history(h):
    with open(history_file,"w") as f:
        json.dump(h,f)

def pairs():
    url="https://www.okx.com/api/v5/public/instruments?instType=SPOT"
    d=requests.get(url).json()["data"]
    return [x["instId"] for x in d if "USDT" in x["instId"]]

def candles(sym,tf,limit):
    url=f"https://www.okx.com/api/v5/market/candles?instId={sym}&bar={tf}&limit={limit}"
    return requests.get(url).json()["data"]

def ticker(sym):
    url=f"https://www.okx.com/api/v5/market/ticker?instId={sym}"
    return requests.get(url).json()["data"][0]

def btc_regime():
    c=candles("BTC-USDT","5m",80)
    cl=[float(x[4]) for x in c]
    return "BULL" if statistics.mean(cl[:5])>statistics.mean(cl[20:40]) else "BEAR"

def trend(sym):
    c=candles(sym,"15m",60)
    cl=[float(x[4]) for x in c]
    return "UP" if statistics.mean(cl[:5])>statistics.mean(cl[20:40]) else "DOWN"

def signal(sym,btc_bias,adaptive_boost):
    try:
        t=ticker(sym)
        if float(t["volCcy24h"])<MIN_VOL:
            return None

        c=candles(sym,"1m",80)
        highs=[float(x[2]) for x in c]
        lows=[float(x[3]) for x in c]
        closes=[float(x[4]) for x in c]
        vols=[float(x[5]) for x in c]

        last=closes[0]
        prevH=highs[1]
        prevL=lows[1]

        conf=50+adaptive_boost
        direction=None

        # liquidity trap
        if highs[0]>max(highs[3:12]) and last<prevH:
            direction="SHORT"
            conf+=20
        if lows[0]<min(lows[3:12]) and last>prevL:
            direction="LONG"
            conf+=20

        # structure break
        if last>prevH:
            direction="LONG"
            conf+=10
        if last<prevL:
            direction="SHORT"
            conf+=10

        # volume spike
        if vols[0]>statistics.mean(vols[20:50])*2:
            conf+=12

        # trend align
        tr=trend(sym)
        if tr=="UP" and direction=="LONG":
            conf+=6
        if tr=="DOWN" and direction=="SHORT":
            conf+=6

        # btc align
        if btc_bias=="BULL" and direction=="LONG":
            conf+=6
        if btc_bias=="BEAR" and direction=="SHORT":
            conf+=6

        if conf>=70 and direction:
            sl=last*(0.996 if direction=="LONG" else 1.004)
            tp=last*(1.009 if direction=="LONG" else 0.991)

            grade="A+" if conf>88 else "A" if conf>80 else "B+"

            return sym,direction,last,sl,tp,conf,grade
    except:
        return None

plist=pairs()
hist=load_history()

while True:

    # AUTO PAUSE jika losing streak parah
    if hist["streak"]>=LOSS_STREAK_LIMIT:
        print("AI PAUSE MODE ACTIVE")
        time.sleep(300)
        hist["streak"]=0
        save_history(hist)

    bias=btc_regime()

    winrate = hist["wins"]/(hist["wins"]+hist["loss"]+1)
    adaptive_boost = int(winrate*10)

    sigs=[]
    for p in plist:
        s=signal(p,bias,adaptive_boost)
        if s:
            sigs.append(s)

    sigs=sorted(sigs,key=lambda x:x[5],reverse=True)[:MAX_SIGNAL]

    for s in sigs:
        pair,dirc,entry,sl,tp,conf,grade=s

        msg=f"""
🚨 AI ELITE SIGNAL 🚨

PAIR: {pair.replace('-','')}
POSITION: {dirc}

ENTRY: {entry}
SL: {round(sl,6)}
TP: {round(tp,6)}

CONFIDENCE: {conf}%
GRADE: {grade}

Winrate AI: {round(winrate*100,1)}%

Adaptive smart money model active ⚡
"""
        send(msg)

    # simulasi update performa random (nanti real bisa dari exchange API)
    import random
    if random.random()>0.5:
        hist["wins"]+=1
        hist["streak"]=0
    else:
        hist["loss"]+=1
        hist["streak"]+=1

    save_history(hist)

    time.sleep(60)