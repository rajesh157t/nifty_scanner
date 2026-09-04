import yfinance as yf
import asyncio
import pytz
import os
import threading
from datetime import datetime
from telegram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from flask import Flask
import pandas as pd

TOKEN = os.environ.get("8796819926:AAHcbZ6ZMbgVH6ifPAzUwHFFipnw1nulJZo")
CHAT_ID = os.environ.get("1133256294")

# yfinance ke liye ticker fix
TICKER_FIX = {"M&M": "M_M"}

FNO_MAP = {
"RELIANCE":"Oil","HDFCBANK":"Bank","ICICIBANK":"Bank","SBIN":"Bank","INFY":"IT","TCS":"IT",
"LT":"Infra","BHARTIARTL":"Telecom","ITC":"FMCG","AXISBANK":"Bank","KOTAKBANK":"Bank","BAJFINANCE":"Finance",
"ASIANPAINT":"Paint","MARUTI":"Auto","M&M":"Auto","TITAN":"Consumer","SUNPHARMA":"Pharma","ULTRACEMCO":"Cement",
"NTPC":"Power","ONGC":"Oil","POWERGRID":"Power","HCLTECH":"IT","WIPRO":"IT","ADANIENT":"Metals",
"ADANIPORTS":"Infra","JSWSTEEL":"Metals","TATASTEEL":"Metals","HINDALCO":"Metals","COALINDIA":"Oil","BPCL":"Oil",
"BAJAJFINSV":"Finance","SBILIFE":"Insurance","HDFCLIFE":"Insurance","GRASIM":"Cement","CIPLA":"Pharma","DRREDDY":"Pharma",
"DIVISLAB":"Pharma","EICHERMOT":"Auto","HEROMOTOCO":"Auto","BAJAJ-AUTO":"Auto","BRITANNIA":"FMCG","NESTLEIND":"FMCG",
"TATACONSUM":"FMCG","HINDUNILVR":"FMCG","APOLLOHOSP":"Healthcare","BEL":"Defence","HAL":"Defence","TRENT":"Retail",
"INDUSINDBK":"Bank","BANKBARODA":"Bank","PNB":"Bank","FEDERALBNK":"Bank","IDFCFIRSTB":"Bank","SHRIRAMFIN":"Finance",
"CHOLAFIN":"Finance","MUTHOOTFIN":"Finance","PERSISTENT":"IT","TECHM":"IT","COFORGE":"IT",
"DLF":"Realty","GODREJPROP":"Realty","INDIGO":"Aviation"
}

bot = Bot(token=TOKEN)
app = Flask(__name__)

@app.route('/')
def home():
    return "PRO Bot LIVE - Fixed"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1/period, min_periods=period).mean()
    loss = -delta.where(delta < 0, 0).ewm(alpha=1/period, min_periods=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_batch_data():
    symbols = [f"{TICKER_FIX.get(s, s)}.NS" for s in FNO_MAP.keys()]
    try:
        df = yf.download(symbols, period="6mo", group_by='ticker', auto_adjust=True, progress=False, threads=True, timeout=20)
        return df
    except Exception as e:
        print(f"Download failed: {e}")
        return None

def check_already_sent():
    ist = pytz.timezone('Asia/Kolkata')
    today = datetime.now(ist).strftime("%Y-%m-%d")
    if os.path.exists("last_sent.txt"):
        with open("last_sent.txt", "r") as f:
            if f.read().strip() == today:
                return True
    return False

def mark_sent():
    ist = pytz.timezone('Asia/Kolkata')
    today = datetime.now(ist).strftime("%Y-%m-%d")
    with open("last_sent.txt", "w") as f:
        f.write(today)

async def check_fno():
    if check_already_sent():
        print("Already sent today, skipping")
        return

    ist = pytz.timezone('Asia/Kolkata')
    time_now = datetime.now(ist).strftime("%d %b %I:%M %p")

    print("Downloading data...")
    raw_df = await asyncio.to_thread(get_batch_data)
    if raw_df is None or raw_df.empty:
        print("No data")
        return

    candidates = []
    # raw_df is MultiIndex when batch
    for sym, sector in FNO_MAP.items():
        yf_sym = f"{TICKER_FIX.get(sym, sym)}.NS"
        try:
            if yf_sym in raw_df.columns.get_level_values(0):
                df = raw_df[yf_sym].dropna()
            else:
                # Fallback for single ticker structure
                df = raw_df.dropna()
                if len(df) < 50: continue

            if len(df) < 50: continue

            vol = float(df['Volume'].iloc[-1])
            avg20 = float(df['Volume'].rolling(20).mean().iloc[-1])
            if avg20 == 0: continue
            ratio = vol / avg20
            if ratio < 1.5: continue

            close = float(df['Close'].iloc[-1])
            prev = float(df['Close'].iloc[-2])
            chg = (close - prev) / prev * 100
            rsi = float(calc_rsi(df['Close']).iloc[-1])
            high_52 = float(df['High'].max())
            high_pct = (close / high_52) * 100

            score = ratio * 10 + abs(chg) * 2 + (high_pct / 10)

            if rsi > 68 and high_pct > 95: tag = "BREAKOUT 🚀"
            elif rsi < 60 and ratio > 1.8: tag = "ACCUMULATION 🟢"
            else: tag = "MOMENTUM ⚡"

            candidates.append((score, ratio, chg, rsi, high_pct, sym, sector, tag))
        except Exception as e:
            print(f"Error {sym}: {e}")
            continue

    candidates.sort(reverse=True, key=lambda x: x[0])

    msg = f"🔥 PRO ALERT {time_now}\n\nTOP 3 BEST SHARES:\n\n"
    if not candidates:
        msg += "Aaj koi blast nahi - Market dull hai"
    else:
        for score, ratio, chg, rsi, high_pct, sym, sector, tag in candidates[:3]:
            msg += f"*{sym}* | {sector}\n"
            msg += f"Vol {ratio:.2f}x | {chg:+.2f}% | RSI {rsi:.0f} | 52W {high_pct:.0f}%\n"
            msg += f"=> {tag} (Score {score:.0f})\n\n"

    try:
        await bot.initialize()
        await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')
        mark_sent()
        print("Sent!")
    except Exception as e:
        print(f"Telegram error: {e}")

async def main():
    scheduler = AsyncIOScheduler(timezone='Asia/Kolkata')
    scheduler.add_job(check_fno, 'cron', hour=15, minute=35, day_of_week='mon-fri')
    scheduler.start()
    print("Scheduler started")
    await check_fno()
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
