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

TOKEN = os.environ.get("TOKEN", "8796819926:AAFWziABJAdsOZ-RO5XO3H7_waIpdrdb-xU")
CHAT_ID = os.environ.get("CHAT_ID", "1133256294")

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
# ... tera baki code ...
 __name__ == "__main__":
    # bot start
    
    @app.route('/')
def home():
    return "PRO Bot LIVE"

def run_flask():
    # Render ke liye 0.0.0.0 aur PORT env compulsory
    port = int(os.environ.get("PORT", 10000))
    print(f"Flask running on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)


def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_data(symbol):
    try:
        df = yf.download(symbol, period="1y", progress=False, auto_adjust=True, threads=False)
        if df.empty or len(df) < 50:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except:
        return None

last_sent_date = None

async def check_fno():
    global last_sent_date
    ist = pytz.timezone('Asia/Kolkata')
    today_str = datetime.now(ist).strftime("%Y-%m-%d")
    if last_sent_date == today_str:
        print("Already sent today")
        return
    last_sent_date = today_str
    time_now = datetime.now(ist).strftime("%d %b %I:%M %p")
    candidates = []
    for sym, sector in FNO_MAP.items():
        df = await asyncio.to_thread(get_data, sym + ".NS")
        if df is None:
            continue
        try:
            vol = float(df['Volume'].iloc[-1])
            avg20 = float(df['Volume'].rolling(20).mean().iloc[-1])
            if avg20 == 0:
                continue
            ratio = vol / avg20
            if ratio < 1.5:
                continue
            close = float(df['Close'].iloc[-1])
            prev = float(df['Close'].iloc[-2])
            chg = (close - prev) / prev * 100
            rsi = float(calc_rsi(df['Close']).iloc[-1])
            high_52 = float(df['High'].max())
            high_pct = (close / high_52) * 100
            score = ratio * 10 + abs(chg) * 2 + (high_pct / 10)
            if rsi > 68 and high_pct > 95:
                tag = "BREAKOUT"
            elif rsi < 60 and ratio > 1.8:
                tag = "ACCUMULATION"
            else:
                tag = "MOMENTUM"
            candidates.append((score, ratio, chg, rsi, high_pct, sym, sector, tag))
        except Exception as e:
            print(f"Error {sym}: {e}")
            continue
    candidates.sort(reverse=True, key=lambda x: x[0])
    msg = f"PRO ALERT {time_now}\nFII/DII NA |\n\nTOP 3 BEST SHARES:\n\n"
    if not candidates:
        msg += "Aaj koi blast nahi"
    else:
        for score, ratio, chg, rsi, high_pct, sym, sector, tag in candidates[:3]:
            msg += f"{sym} | {sector}\n"
            msg += f"Vol {ratio:.2f}x | {chg:+.2f}% | RSI {rsi:.0f} | High se {high_pct:.0f}%\n"
            msg += f"=> {tag} (Score {score:.0f})\n\n"
    await bot.send_message(chat_id=CHAT_ID, text=msg)

async def main():
    scheduler = AsyncIOScheduler(timezone='Asia/Kolkata')
    scheduler.add_job(check_fno, 'cron', hour=15, minute=35, day_of_week='mon-fri')
    scheduler.start()
    await check_fno()
    while True:
        await asyncio.sleep(3600)

if _name_ == "_main_":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
