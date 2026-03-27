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
PORT = int(os.getenv("PORT", 8080))

# --- KEAMANAN: WHITELIST SYSTEM ---
RAW_WHITELIST = os.getenv("WHITELIST_IDS", "")
WHITELIST_IDS = [int(i.strip()) for i in RAW_WHITELIST.split(",") if i.strip().isdigit()]

ACTIVE_SIGNALS = []
TRADE_HISTORY = [] 
COOLDOWN_COINS = {} 
LEVERAGE = 20

# Blacklist Koin Stable yang mengganggu data market
STABLE_COINS = ["USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "DAIUSDT", "AEURUSDT", "EURUSDT", "GBPUSDT", "BUSDUSDT", "USDPUSDT", "USD1USDT", "USDTUSDT", "UUSDT", "RLUSDUSDT"]
GROQ_MODEL = "llama-3.3-70b-versatile"

bot = telebot.TeleBot(TOKEN_TELEGRAM, threaded=True, num_threads=15)
client_groq = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
app = Flask(__name__)

# --- DASHBOARD HTML (ULTRA-LUXURY) ---
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
        .target-hit { border-color: #ffcc00 !important; color: #ffcc00 !important; background: rgba(255, 204, 0, 0.15); box-shadow: inset 0 0 10px #ffcc00; font-weight: bold; }
    </style>
    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
</head>
<body>
    <div class="app-container">
        <div class="app-header"><h1>NEXUS QUANTUM CORE</h1></div>
        {% if signals %}{% for s in signals %}
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
        {% endfor %}{% else %}<div style="text-align:center; color:#222; margin-top:100px;">[ SCANNING BINANCE FUTURES ]</div>{% endif %}
    </div>
    <script>
        function openModal(symbol, reason) { alert(reason); }
        setInterval(() => { location.reload(); }, 30000);
    </script>
</body>
</html>
"""

@app.route('/')
def dashboard(): return render_template_string(HTML_TEMPLATE, signals=ACTIVE_SIGNALS)

# --- DIRECT BINANCE FUTURES ENGINE (FAPI) ---
def call_binance_futures(endpoint):
    url = f"https://fapi.binance.com{endpoint}"
    try:
        response = requests.get(url, timeout=10) 
        if response.status_code == 200: return response.json()
    except: return None
    return None

def get_multi_tf_technical(symbol):
    try:
        # Mengambil klines langsung dari server Futures
        data_4h = call_binance_futures(f"/fapi/v1/klines?symbol={symbol}&interval=4h&limit=15")
        data_1h = call_binance_futures(f"/fapi/v1/klines?symbol={symbol}&interval=1h&limit=30")
        
        if not data_4h or len(data_4h) < 6 or not data_1h or len(data_1h) < 10:
            return "INSUFFICIENT"

        c4h = [{"c": float(x[4])} for x in data_4h]
        trend_4h = "BULLISH" if c4h[-1]['c'] > c4h[-5]['c'] else "BEARISH"
        
        c1h = [{"h": float(x[2]), "l": float(x[3]), "c": float(x[4]), "v": float(x[5])} for x in data_1h]
        price_now = c1h[-1]['c']
        
        # Hitung RSI Mandiri dari data Futures
        prices = [x['c'] for x in c1h]
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = sum([d for d in deltas[-14:] if d > 0]) / 14
        losses = abs(sum([d for d in deltas[-14:] if d < 0]) / 14)
        rsi = 100 - (100 / (1 + (gains/losses))) if losses != 0 else 100

        range_pct = ((max([x['h'] for x in c1h[-20:]]) - min([x['l'] for x in c1h[-20:]])) / price_now) * 100
        
        return {
            "trend_4h": trend_4h, "price_1h": price_now, 
            "rsi": round(rsi, 2), "market_env": "TRENDING" if range_pct > 1.2 else "CHOPPY",
            "volatility": round(range_pct, 2)
        }
    except: return None

def calculate_roi(entry, target, side):
    try:
        entry, target = float(entry), float(target)
        if entry == 0: return 0
        diff = (target - entry) if str(side).upper() == "LONG" else (entry - target)
        return (diff / entry) * 100 * LEVERAGE
    except: return 0

def format_price(val):
    try:
        if val is None or float(val) == 0: return "0"
        val = float(val)
        if val < 0.0001: return f"{val:.10f}".rstrip('0').rstrip('.')
        if val < 1: return f"{val:.6f}".rstrip('0').rstrip('.')
        return f"{val:,.2f}"
    except: return str(val)

# --- AI QUANT LEARNING ---
def get_ai_analysis(coin_data):
    if not client_groq: return None
    symbol, price = coin_data.get('symbol'), float(coin_data.get('lastPrice') or coin_data.get('price', 0))
    tf = get_multi_tf_technical(symbol)
    if tf == "INSUFFICIENT" or tf is None: return "SKIP"

    learning_log = ""
    if TRADE_HISTORY:
        recent = TRADE_HISTORY[-5:]
        learning_log = "\n[PAST PERFORMANCE LOG]:\n" + "\n".join([f"- {r['symbol']}: {r['status']} ({r['roi']:+.1f}%)" for r in recent])

    prompt = f"""
    Role: Senior Quantitative Analyst. Object: {symbol} at {format_price(price)} (Binance Futures).
    Matrix: 4H Trend {tf['trend_4h']}, RSI: {tf['rsi']}, Market {tf['market_env']}.
    {learning_log}

    Task: Berikan Sniper Signal JSON: signal(LONG/SHORT/WAIT), entry, tp1, tp2, tp3, sl, probability(81-99), reason.
    Logic: AMD Architecture, Fibonacci 1.618, NO scientific notation.
    """
    try:
        completion = client_groq.chat.completions.create(model=GROQ_MODEL, messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"}, timeout=25)
        return json.loads(completion.choices[0].message.content)
    except: return None

# --- UI DISPLAY ---
def send_signal_ui(sig_data, target_chat):
    if not sig_data or sig_data == "SKIP": return
    symbol = sig_data.get('symbol')
    side = str(sig_data.get('signal', 'WAIT')).upper()
    entry, tp1, tp2, tp3, sl = sig_data.get('entry', 0), sig_data.get('tp1', 0), sig_data.get('tp2', 0), sig_data.get('tp3', 0), sig_data.get('sl', 0)
    if not symbol or side not in ['LONG', 'SHORT'] or entry == 0: return

    roi1, roi2, roi3 = calculate_roi(entry, tp1, side), calculate_roi(entry, tp2, side), calculate_roi(entry, tp3, side)
    try: prob = int(float(sig_data.get('probability', 85)))
    except: prob = 85
    meter = "█" * (prob // 10) + "░" * (10 - (prob // 10))
    tv_link = f"https://www.tradingview.com/chart/?symbol=BINANCE:{symbol}PERP"

    msg = (
        f"╔══════════════════════╗\n  **NEXUS QUANTUM TERMINAL**\n╚══════════════════════╝\n\n"
        f"⬥ **IDENTIFIER:** `#{symbol}` (FUTURES)\n⬥ **EXECUTION:** `{side} VECTOR`\n"
        f"⬥ **STRENGTH:** `[{meter}] {prob}%` \n━━━━━━━━━━━━━━━━━━━━\n"
        f"┌─── **ENTRY CORRIDOR** ───┐\n   ` {format_price(entry)} `\n└──────────────────────┘\n\n"
        f"⬥ **QUANTITATIVE TARGETS**\n  ├─ **T1:** `{format_price(tp1)}` (`{roi1:+.1f}%`)\n"
        f"  ├─ **T2:** `{format_price(tp2)}` (`{roi2:+.1f}%`)\n  └─ **T3:** `{format_price(tp3)}` (`{roi3:+.1f}%`)\n\n"
        f"⬥ **RISK MITIGATION (SL)**\n  └─ `{format_price(sl)}` (Isolated 20x)\n━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 **NEURAL REASONING:**\n_{sig_data.get('reason', 'Confirmed.')}_\n\n"
        f"🔗 [ACCESS REAL-TIME DATA HUB]({tv_link})\n━━━━━━━━━━━━━━━━━━━━\n"
        f"**SMC GLOBAL • INSTITUTIONAL GRADE**"
    )
    bot.send_message(target_chat, msg, parse_mode="Markdown", disable_web_page_preview=False)
    if not any(s.get('symbol') == symbol for s in ACTIVE_SIGNALS): ACTIVE_SIGNALS.append(sig_data)

# --- MONITORING: TP1-2-3 & SL ---
def monitor_active_signals():
    global ACTIVE_SIGNALS, TRADE_HISTORY, COOLDOWN_COINS
    while True:
        try:
            for sig in ACTIVE_SIGNALS[:]:
                symbol, entry, side = sig['symbol'], float(sig['entry']), sig['signal'].upper()
                tp1, tp2, tp3, sl = float(sig['tp1']), float(sig['tp2']), float(sig['tp3']), float(sig['sl'])
                
                # Mengambil harga dari Futures Price API
                res = call_binance_futures(f"/fapi/v1/ticker/price?symbol={symbol}")
                if not res: continue
                curr, roi = float(res['price']), calculate_roi(entry, float(res['price']), side)

                is_finished, status = False, ""
                if (side == "LONG" and curr <= sl) or (side == "SHORT" and curr >= sl):
                    status, is_finished = "🛑 SL HIT", True
                elif (side == "LONG" and curr >= tp3) or (side == "SHORT" and curr <= tp3):
                    status, is_finished = "🎯 TP3 HIT", True
                elif (side == "LONG" and curr >= tp2) or (side == "SHORT" and curr <= tp2):
                    if not sig.get('tp2_n'): bot.send_message(CHAT_ID, f"✅ **T2 HIT** #{symbol}"); sig['tp2_n'] = True
                elif (side == "LONG" and curr >= tp1) or (side == "SHORT" and curr <= tp1):
                    if not sig.get('tp1_n'): bot.send_message(CHAT_ID, f"✅ **T1 HIT** #{symbol}"); sig['tp1_n'] = True

                if is_finished:
                    bot.send_message(CHAT_ID, f"{status} #{symbol} ROI: {roi:+.1f}%\nExit: {format_price(curr)}")
                    TRADE_HISTORY.append({"symbol": symbol, "roi": roi, "status": status, "timestamp": datetime.now(timezone.utc).isoformat()})
                    COOLDOWN_COINS[symbol] = datetime.now(timezone.utc) + timedelta(hours=4); ACTIVE_SIGNALS.remove(sig)
            time.sleep(60) 
        except: time.sleep(60)

# --- SCANNER OTOMATIS ---
def run_scanner():
    global COOLDOWN_COINS
    # Mengambil ticker koin yang ada di Futures saja
    res = call_binance_futures("/fapi/v1/ticker/24hr")
    if not res: return
    now = datetime.now(timezone.utc); COOLDOWN_COINS = {k: v for k, v in COOLDOWN_COINS.items() if v > now}
    
    # Filter koin berpasangan USDT yang bukan stablecoin
    valid = [c for c in res if c['symbol'].endswith("USDT") and c['symbol'] not in STABLE_COINS and float(c['quoteVolume']) > 15000000]
    
    targets = sorted(valid, key=lambda x: float(x['priceChangePercent']), reverse=True)[:4] + sorted(valid, key=lambda x: float(x['priceChangePercent']))[:4]
    for t in {v['symbol']:v for v in targets}.values():
        if any(s.get('symbol') == t['symbol'] for s in ACTIVE_SIGNALS) or t['symbol'] in COOLDOWN_COINS: continue
        sig = get_ai_analysis(t)
        if sig and sig != "SKIP":
            send_signal_ui(sig, CHAT_ID)
            time.sleep(15) 

# --- HANDLERS ---
def is_authorized(uid): return not WHITELIST_IDS or uid in WHITELIST_IDS
def denied_access(message): bot.reply_to(message, "❌ **ACCESS DENIED**")

@bot.message_handler(commands=['start'])
def start(message):
    if not is_authorized(message.from_user.id): return denied_access(message)
    m = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True); m.add(KeyboardButton("🛰️ INITIATE SCAN"), KeyboardButton("🖥️ CORE STATUS"))
    bot.send_message(message.chat.id, "⚡ **NEXUS QUANTUM CORE ONLINE**", reply_markup=m)

@bot.message_handler(func=lambda m: m.text == "🛰️ INITIATE SCAN")
def manual_scan(message):
    if not is_authorized(message.from_user.id): return denied_access(message)
    bot.reply_to(message, "🔄 `INITIATING_ASYNC_SCANNER...`")
    threading.Thread(target=run_scanner).start()

@bot.message_handler(func=lambda m: m.text == "🖥️ CORE STATUS")
def status_btn(message):
    if not is_authorized(message.from_user.id): return denied_access(message)
    bot.send_message(message.chat.id, f"🟢 **SYSTEM DIAGNOSTICS: OPTIMAL**\n🎯 Signals Monitored: {len(ACTIVE_SIGNALS)}")

@bot.message_handler(func=lambda m: m.text.lower().startswith('cek'))
def manual_check(message):
    if not is_authorized(message.from_user.id): return denied_access(message)
    try:
        coin = "".join(re.findall(r'[A-Z0-9]', message.text.split()[1].upper())); symbol = f"{coin}USDT"
        # Cek koin langsung ke API Futures
        res = call_binance_futures(f"/fapi/v1/ticker/24hr?symbol={symbol}")
        if res:
            sig = get_ai_analysis(res)
            if sig and sig != "SKIP": send_signal_ui(sig, message.chat.id)
            else: bot.send_message(message.chat.id, f"⚠️ `INSUFFICIENT DATA / CHOPPY:` {symbol}")
        else: bot.send_message(message.chat.id, f"❌ `NOT FOUND IN FUTURES:` {symbol}")
    except: pass

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=PORT, use_reloader=False), daemon=True).start()
    threading.Thread(target=monitor_active_signals, daemon=True).start()
    def scheduler():
        while True:
            run_scanner()
            time.sleep(1800)
    threading.Thread(target=scheduler, daemon=True).start()
    bot.infinity_polling(skip_pending=True)