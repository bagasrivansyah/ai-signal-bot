import os
import requests
import telebot
import json
import time
import threading
import re
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template_string
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from groq import Groq 

# === CONFIGURATION ===
TOKEN_TELEGRAM = os.getenv("TOKEN_TELEGRAM")
CHAT_ID = os.getenv("CHAT_ID") or os.getenv("ID_CHAT_TELEGRAM")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
COINGLASS_API_KEY = os.getenv("COINGLASS_API_KEY")
PORT = int(os.getenv("PORT", 8080))

# --- KEAMANAN: WHITELIST SYSTEM (OS VAR) ---
RAW_WHITELIST = os.getenv("WHITELIST_IDS", "")
WHITELIST_IDS = [int(i.strip()) for i in RAW_WHITELIST.split(",") if i.strip().isdigit()]

ACTIVE_SIGNALS = []
TRADE_HISTORY = [] 
COOLDOWN_COINS = {} 
LEVERAGE = 20

STABLE_COINS = ["USDC", "FDUSD", "TUSD", "DAI", "AEUR", "EUR", "GBP", "BUSD", "USDP", "USD1", "USDT", "UUSDT", "RLUSD"]
GROQ_MODEL = "llama-3.3-70b-versatile"

bot = telebot.TeleBot(TOKEN_TELEGRAM, threaded=True, num_threads=20)
client_groq = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
app = Flask(__name__)

# --- DASHBOARD HTML (ULTRA-LUXURY DESIGN FOR APK) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>NEXUS QUANTUM</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=JetBrains+Mono&display=swap');
        body { background-color: #000; color: #00ff88; font-family: 'JetBrains Mono', monospace; margin: 0; padding: 0; overflow-x: hidden; background-image: radial-gradient(circle at 50% 50%, #0a2a1a 0%, #000 100%); }
        body::before { content: " "; display: block; position: fixed; top: 0; left: 0; bottom: 0; right: 0; background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.25) 50%), linear-gradient(90deg, rgba(255, 0, 0, 0.06), rgba(0, 255, 0, 0.02), rgba(0, 0, 255, 0.06)); z-index: 9999; width: 100%; height: 100%; background-size: 100% 2px, 3px 100%; pointer-events: none; }
        .app-container { padding: 20px; max-width: 500px; margin: auto; }
        .app-header { text-align: center; padding: 20px 0; border-bottom: 1px solid #00ff88; margin-bottom: 25px; }
        .app-header h1 { font-family: 'Orbitron', sans-serif; font-size: 20px; margin: 0; letter-spacing: 5px; text-shadow: 0 0 10px #00ff88; }
        .signal-card { background: rgba(10, 10, 10, 0.8); border: 1px solid #333; margin-bottom: 20px; position: relative; padding: 15px; cursor: pointer; }
        .signal-card::after { content: ""; position: absolute; top: 0; left: 0; width: 4px; height: 100%; background: #00ff88; }
        .signal-card.short::after { background: #ff4444; }
        .entry-price { font-size: 24px; text-align: center; color: #00ccff; margin: 10px 0; border: 1px dashed #333; padding: 10px; }
        .target-box { font-size: 10px; text-align: center; border: 1px solid #222; padding: 5px; transition: 0.5s; }
        .target-hit { border-color: #ffcc00 !important; color: #ffcc00 !important; background: rgba(255, 204, 0, 0.15); box-shadow: inset 0 0 10px #ffcc00; }
        #modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.98); z-index: 10000; overflow-y: auto; }
        #alert-init-btn { width: 100%; padding: 12px; background: #00ff88; color: #000; border: none; font-family: 'Orbitron'; font-weight: bold; cursor: pointer; margin-bottom: 20px; box-shadow: 0 0 15px #00ff88; }
    </style>
    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
</head>
<body>
    <div class="app-container">
        <button id="alert-init-btn" onclick="initSystem()">[ ACTIVATE NEURAL INTERFACE ]</button>
        <div class="app-header"><h1>NEXUS QUANTUM</h1></div>
        {% for s in signals %}
        <div class="signal-card {{ 'short' if s.signal == 'SHORT' else '' }}" onclick="openModal('{{ s.symbol }}', '{{ s.reason }}')">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div style="font-family:'Orbitron'; font-size:18px; color:white;">#{{ s.symbol }}</div>
                <div style="font-size: 10px; padding: 2px 8px; background: {{ '#00ff88' if s.signal == 'LONG' else '#ff4444' }}; color: #000; font-weight: bold;">{{ s.signal }} VECTOR</div>
            </div>
            <div class="entry-price">{{ s.entry }}</div>
            <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:10px; margin-top: 15px;">
                <div class="target-box {{ 'target-hit' if s.get('tp1_n') else '' }}">T1<span>{{ s.tp1 }}</span></div>
                <div class="target-box {{ 'target-hit' if s.get('tp2_n') else '' }}">T2<span>{{ s.tp2 }}</span></div>
                <div class="target-box {{ 'target-hit' if s.get('tp3_n') else '' }}">T3<span>{{ s.tp3 }}</span></div>
            </div>
        </div>
        {% endfor %}
    </div>
    <div id="modal">
        <div style="padding:20px; max-width:500px; margin:auto;">
            <div onclick="closeModal()" style="color:#ff4444; text-align:right; cursor:pointer; font-family: 'Orbitron'; font-size: 14px;">[ CLOSE_TERMINAL X ]</div>
            <div id="chart-div" style="height:320px; margin:20px 0; border: 1px solid #333;"></div>
            <div id="reason-content" style="color:#ccc; font-size:13px; line-height:1.6; border:1px solid #00ff88; padding:15px; background:#050505;"></div>
        </div>
    </div>
    <audio id="newSigBeep" src="https://assets.mixkit.co/active_storage/sfx/2568/2568-preview.mp3"></audio>
    <audio id="hitChime" src="https://assets.mixkit.co/active_storage/sfx/1435/1435-preview.mp3"></audio>
    <script>
        function initSystem() { document.getElementById('alert-init-btn').style.display = 'none'; }
        function openModal(symbol, reason) {
            document.getElementById('modal').style.display = 'block';
            document.getElementById('reason-content').innerText = reason;
            new TradingView.widget({ "width": "100%", "height": 320, "symbol": "BINANCE:" + symbol + "PERP", "interval": "60", "theme": "dark", "style": "1", "container_id": "chart-div", "hide_top_toolbar": true });
        }
        function closeModal() { document.getElementById('modal').style.display = 'none'; document.getElementById('chart-div').innerHTML = ""; }
        setInterval(() => { if(document.getElementById('modal').style.display !== 'block') location.reload(); }, 25000);
    </script>
</body>
</html>
"""

@app.route('/')
def dashboard(): return render_template_string(HTML_TEMPLATE, signals=ACTIVE_SIGNALS)

# --- COINGLASS V4 API TOOLS ---
def call_coinglass_v4(endpoint, params=None):
    url = f"https://open-api-v4.coinglass.com{endpoint}"
    headers = {"accept": "application/json", "CG-API-KEY": COINGLASS_API_KEY}
    try:
        res = requests.get(url, headers=headers, params=params, timeout=15)
        return res.json() if res.status_code == 200 else None
    except: return None

def get_market_intel(symbol):
    coin = symbol.replace("USDT", "").upper()
    try:
        # Ambil OHLC dan Price via V4
        res = call_coinglass_v4("/api/v1/futures/openInterest/ohlc", {"symbol": coin, "interval": "h1"})
        if not res or not res.get('data'): return None
        latest = res['data'][-1]
        # Ambil Long/Short Ratio
        ls_res = call_coinglass_v4("/api/v1/futures/longShort_chart", {"symbol": coin, "interval": "h1"})
        ls_data = ls_res['data'][-1] if ls_res and ls_res.get('data') else {"longShortRatio": 1, "longRate": 50, "shortRate": 50}
        
        return {
            "price": latest.get('close', 0),
            "oi": latest.get('openInterest', 0),
            "ls_ratio": ls_data.get('longShortRatio'),
            "long_rate": ls_data.get('longRate'),
            "short_rate": ls_data.get('shortRate'),
            "h": latest.get('high'), "l": latest.get('low')
        }
    except: return None

# --- TECHNICAL ENGINE (V4 DATA) ---
def get_multi_tf_technical(symbol):
    try:
        # Menggunakan V4 OHLC untuk simulasi Multi-TF
        data_4h = call_coinglass_v4("/api/v1/futures/openInterest/ohlc", {"symbol": symbol.replace("USDT",""), "interval": "h4"})
        data_1h = call_coinglass_v4("/api/v1/futures/openInterest/ohlc", {"symbol": symbol.replace("USDT",""), "interval": "h1"})
        if not data_4h or not data_1h: return "INSUFFICIENT"
        
        c4h = data_4h['data']
        c1h = data_1h['data']
        trend_4h = "BULLISH" if c4h[-1]['close'] > c4h[-5]['close'] else "BEARISH"
        
        # Deteksi Choppy
        recent_h = max([x['high'] for x in c1h[-20:]])
        recent_l = min([x['low'] for x in c1h[-20:]])
        range_pct = ((recent_h - recent_l) / c1h[-1]['close']) * 100
        
        return {
            "trend_4h": trend_4h, "price_1h": c1h[-1]['close'], 
            "market_env": "TRENDING" if range_pct > 1.2 else "CHOPPY",
            "range_pct": range_pct, "high_24h": recent_h, "low_24h": recent_l
        }
    except: return None

def format_price(val):
    try:
        if val is None or float(val) == 0: return "0"
        v = float(val)
        return f"{v:.10f}".rstrip('0').rstrip('.') if v < 0.001 else f"{v:,.4f}"
    except: return str(val)

def calculate_roi(entry, target, side):
    try:
        e, t = float(entry), float(target)
        if e == 0: return 0
        diff = (t - e) if str(side).upper() == "LONG" else (e - t)
        return (diff / e) * 100 * LEVERAGE
    except: return 0

# --- AI SNIPER ENGINE (QUANT LEARNING) ---
def get_ai_analysis(coin_data):
    if not client_groq: return None
    symbol = coin_data.get('symbol')
    intel = get_market_intel(symbol)
    tf = get_multi_tf_technical(symbol)
    if not intel or not tf or tf == "INSUFFICIENT": return "SKIP"

    learning_log = "\n".join([f"- {r['symbol']}: {r['status']}" for r in TRADE_HISTORY[-5:]])
    win_rate = (len([t for t in TRADE_HISTORY if t['roi'] > 0]) / len(TRADE_HISTORY)) * 100 if TRADE_HISTORY else 0

    prompt = f"""
    Role: Lead Quant Strategist. Object: {symbol} at ${format_price(intel['price'])}.
    [V4 INTEL] OI: {intel['oi']}, LS Ratio: {intel['ls_ratio']}, 4H Trend: {tf['trend_4h']}, Market: {tf['market_env']}.
    [METRICS] WinRate: {win_rate:.1f}%. History: {learning_log}
    Task: Sniper Signal JSON. Rules: AMD Logic, Fibonacci 1.618, dynamic prob 81-99%. No scientific notation. Retrace-Entry.
    Output JSON ONLY: {{"symbol": "{symbol}", "signal": "LONG/SHORT/WAIT", "entry": 0, "tp1": 0, "tp2": 0, "tp3": 0, "sl": 0, "probability": 0, "reason": "SMC V4 reasoning."}}
    """
    try:
        completion = client_groq.chat.completions.create(model=GROQ_MODEL, messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"}, timeout=25)
        res = json.loads(completion.choices[0].message.content)
        res['oi'] = intel['oi']
        return res
    except: return None

# --- UI DISPLAY (BLACK-BOX) ---
def send_signal_ui(sig_data, target_chat):
    if not sig_data or sig_data == "SKIP": return
    symbol, side = sig_data.get('symbol'), str(sig_data.get('signal', 'WAIT')).upper()
    entry, tp1, tp2, tp3, sl = sig_data.get('entry', 0), sig_data.get('tp1', 0), sig_data.get('tp2', 0), sig_data.get('tp3', 0), sig_data.get('sl', 0)
    if not symbol or side not in ['LONG', 'SHORT'] or entry == 0: return

    roi1, roi2, roi3 = calculate_roi(entry, tp1, side), calculate_roi(entry, tp2, side), calculate_roi(entry, tp3, side)
    try: prob = int(float(sig_data.get('probability', 85)))
    except: prob = 85
    meter = "█" * (prob // 10) + "░" * (10 - (prob // 10))
    tv_link = f"https://www.tradingview.com/chart/?symbol=BINANCE:{symbol}PERP"

    msg = (
        f"╔══════════════════════╗\n  **NEXUS QUANTUM TERMINAL**\n╚══════════════════════╝\n\n"
        f"⬥ **IDENTIFIER:** `#{symbol}` (V4_DATA)\n⬥ **EXECUTION:** `{side} VECTOR`\n"
        f"⬥ **INSTITUTIONAL OI:** `${format_price(sig_data.get('oi', 0))}`\n"
        f"⬥ **STRENGTH:** `[{meter}] {prob}%` \n━━━━━━━━━━━━━━━━━━━━\n"
        f"┌─── **ENTRY CORRIDOR** ───┐\n   ` {format_price(entry)} `\n└──────────────────────┘\n\n"
        f"⬥ **QUANTITATIVE TARGETS**\n"
        f"  ├ T1: `{format_price(tp1)}` ({roi1:+.1f}%)\n"
        f"  ├ T2: `{format_price(tp2)}` \n"
        f"  └ T3: `{format_price(tp3)}` \n\n"
        f"⬥ **RISK MITIGATION (SL)**\n"
        f"  └ `{format_price(sl)}` (Isolated 20x)\n━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 **NEURAL REASONING:**\n_{sig_data.get('reason', 'Confirmed.')}_\n\n"
        f"🔗 [ACCESS REAL-TIME DATA HUB]({tv_link})\n━━━━━━━━━━━━━━━━━━━━\n"
        f"**SMC GLOBAL • V4 LIQUIDITY ENGINE**"
    )
    bot.send_message(target_chat, msg, parse_mode="Markdown", disable_web_page_preview=False)
    if not any(s.get('symbol') == symbol for s in ACTIVE_SIGNALS): ACTIVE_SIGNALS.append(sig_data)

# --- HANDLERS & MONITORING ---
def is_authorized(uid): return not WHITELIST_IDS or uid in WHITELIST_IDS
def denied_access(message): bot.reply_to(message, "❌ **ACCESS DENIED**")

@bot.message_handler(commands=['start'])
def start(message):
    if not is_authorized(message.from_user.id): return denied_access(message)
    m = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True); m.add(KeyboardButton("🛰️ INITIATE SCAN"), KeyboardButton("🖥️ CORE STATUS"))
    bot.send_message(message.chat.id, "⚡ **NEXUS QUANTUM CORE ONLINE**", reply_markup=m)

@bot.message_handler(func=lambda m: m.text == "🛰️ INITIATE SCAN")
def man_scan(message):
    if not is_authorized(message.from_user.id): return denied_access(message)
    bot.reply_to(message, "🔄 `INITIATING_V4_SCANNER...`")
    threading.Thread(target=run_scanner).start()

@bot.message_handler(func=lambda m: m.text == "🖥️ CORE STATUS")
def status(message):
    if not is_authorized(message.from_user.id): return denied_access(message)
    bot.send_message(message.chat.id, f"🟢 **SYSTEM DIAGNOSTICS: OPTIMAL**\n🎯 Signals Monitored: {len(ACTIVE_SIGNALS)}")

@bot.message_handler(func=lambda m: m.text.lower().startswith('cek'))
def manual_check(message):
    if not is_authorized(message.from_user.id): return denied_access(message)
    try:
        coin = "".join(re.findall(r'[A-Z0-9]', message.text.split()[1].upper())); symbol = f"{coin}USDT"
        res = get_market_intel(symbol)
        if res:
            sig = get_ai_analysis({"symbol": symbol})
            if sig and sig != "SKIP": send_signal_ui(sig, message.chat.id)
            else: bot.send_message(message.chat.id, "⚠️ `INSUFFICIENT LIQUIDITY / CHOPPY`")
        else: bot.send_message(message.chat.id, f"❌ `NOT FOUND IN V4:` {symbol}")
    except: pass

def monitor_active_signals():
    global ACTIVE_SIGNALS, TRADE_HISTORY, COOLDOWN_COINS
    while True:
        try:
            for sig in ACTIVE_SIGNALS[:]:
                symbol, entry, side = sig['symbol'], float(sig['entry']), sig['signal'].upper()
                tp1, tp2, tp3, sl = float(sig['tp1']), float(sig['tp2']), float(sig['tp3']), float(sig['sl'])
                intel = get_market_intel(symbol)
                if not intel: continue
                curr, roi = intel['price'], calculate_roi(entry, intel['price'], side)
                is_fin, status = False, ""
                if (side == "LONG" and curr <= sl) or (side == "SHORT" and curr >= sl): status, is_fin = "🛑 SL HIT", True
                elif (side == "LONG" and curr >= tp3) or (side == "SHORT" and curr <= tp3): status, is_fin = "🎯 TP3 HIT", True
                elif (side == "LONG" and curr >= tp2) or (side == "SHORT" and curr <= tp2):
                    if not sig.get('tp2_n'): bot.send_message(CHAT_ID, f"✅ **T2 HIT** #{symbol} ROI: {roi:+.1f}%"); sig['tp2_n'] = True
                elif (side == "LONG" and curr >= tp1) or (side == "SHORT" and curr <= tp1):
                    if not sig.get('tp1_n'): bot.send_message(CHAT_ID, f"✅ **T1 HIT** #{symbol} ROI: {roi:+.1f}%"); sig['tp1_n'] = True
                if is_fin:
                    bot.send_message(CHAT_ID, f"{status} #{symbol} ROI: {roi:+.1f}%\nExit: {format_price(curr)}")
                    TRADE_HISTORY.append({"symbol": symbol, "roi": roi, "status": status, "timestamp": datetime.now(timezone.utc).isoformat()})
                    COOLDOWN_COINS[symbol] = datetime.now(timezone.utc) + timedelta(hours=4); ACTIVE_SIGNALS.remove(sig)
            time.sleep(60)
        except: time.sleep(60)

def daily_report_scheduler():
    global TRADE_HISTORY
    while True:
        now = datetime.now(timezone.utc)
        if now.hour == 0 and now.minute == 0:
            yesterday = now - timedelta(days=1)
            trades = [t for t in TRADE_HISTORY if datetime.fromisoformat(t['timestamp']) > yesterday]
            if trades:
                total_roi, wr = sum([t['roi'] for t in trades]), (len([t for t in trades if t['roi'] > 0]) / len(trades)) * 100
                bot.send_message(CHAT_ID, f"📊 **NEXUS DAILY QUANT REPORT**\nVectors: {len(trades)}\nWinRate: {wr:.1f}%\nROI: {total_roi:+.2f}%")
            time.sleep(70)
        time.sleep(30)

def run_scanner():
    global COOLDOWN_COINS
    # Mengambil ticker dinamis dari Coinglass V4
    res = call_coinglass_v4("/api/v1/futures/market/ticker", {"asset": "USDT"})
    if not res or not res.get('data'): return
    now = datetime.now(timezone.utc); COOLDOWN_COINS = {k: v for k, v in COOLDOWN_COINS.items() if v > now}
    
    # Filter Gainer & Loser secara dinamis
    valid = [c for c in res['data'] if c['symbol'].endswith("USDT") and c['symbol'].replace("USDT","") not in STABLE_COINS]
    targets = sorted(valid, key=lambda x: float(x.get('priceChangePercent', 0)), reverse=True)[:4] + sorted(valid, key=lambda x: float(x.get('priceChangePercent', 0)))[:4]
    
    for t in targets:
        symbol = t['symbol']
        if any(s.get('symbol') == symbol for s in ACTIVE_SIGNALS) or symbol in COOLDOWN_COINS: continue
        sig = get_ai_analysis(t)
        if sig and sig != "SKIP" and sig.get('signal') in ['LONG', 'SHORT']: send_signal_ui(sig, CHAT_ID); time.sleep(15)

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=PORT, use_reloader=False), daemon=True).start()
    threading.Thread(target=monitor_active_signals, daemon=True).start()
    threading.Thread(target=daily_report_scheduler, daemon=True).start()
    def scheduler():
        while True:
            run_scanner(); time.sleep(1800)
    threading.Thread(target=scheduler, daemon=True).start()
    bot.infinity_polling(skip_pending=True)