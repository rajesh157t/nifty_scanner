import yfinance as yf
import pandas as pd
import time
import os
from flask import Flask
import threading

app = Flask(__name__)

# ===== TELEGRAM (agar use karte ho to token daal dena) =====
BOT_TOKEN = os.getenv("8796819926:AAFWziABJAdsOZ-RO5XO3H7_waIpdrdb-xU", "")
CHAT_ID = os.getenv("1133256294", "")

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def scan_all_stocks(stock_list):
    # IMPORTANT: Ek sath saare stocks download karo - 'records' error fix
    tickers_str = " ".join([s + ".NS" for s in stock_list])
    print(f"Downloading {len(stock_list)} stocks together...")

    try:
        # threads=False se Yahoo block nahi karta
        data = yf.download(tickers_str, period="60d", group_by='ticker', threads=False, auto_adjust=True, progress=False)
    except Exception as e:
        print(f"Download failed: {e}, retrying after 10 sec...")
        time.sleep(10)
        return []

    results = []
    for symbol in stock_list:
        try:
            # Data nikalna
            if len(stock_list) == 1:
                df = data
            else:
                if symbol + ".NS" not in data.columns.levels[0]:
                    print(f"{symbol} data not found")
                    continue
                df = data[symbol + ".NS"]

            if len(df) < 30:
                continue

            df['EMA20'] = df['Close'].ewm(span=20).mean()
            df['EMA50'] = df['Close'].ewm(span=50).mean()
            df['EMA200'] = df['Close'].ewm(span=200).mean()
            df['RSI'] = compute_rsi(df['Close'])
            df['VolAvg20'] = df['Volume'].rolling(20).mean()

            last = df.iloc[-1]

            # ===== VOLUME 1.5x CONDITION - TUMHARI DEMAND =====
            vol_avg = last['VolAvg20']
            vol_ratio = last['Volume'] / vol_avg if vol_avg > 0 else 0
            vol_ok = vol_ratio >= 1.5 and last['Close'] > last['Open']

            trend_ok = last['Close'] > last['EMA200']
            cross_ok = last['EMA20'] > last['EMA50']
            rsi_ok = last['RSI'] > 55

            if vol_ok and trend_ok and cross_ok and rsi_ok:
                print(f"✅ BUY {symbol} | Vol {vol_ratio:.2f}x | RSI {last['RSI']:.1f}")
                results.append(symbol)
            else:
                print(f"Checked {symbol} | Vol {vol_ratio:.2f}x - No match")

        except Exception as e:
            print(f"{symbol} error '{e}' - skipping")
            continue

        time.sleep(0.5)

    return results

def main_loop():
    stocks = ["NTPC", "ONGC", "BAJFINANCE", "LT", "SUNPHARMA", "POWERGRID", "RELIANCE", "TCS", "INFY"]
    while True:
        print("--- Starting new scan ---")
        matches = scan_all_stocks(stocks)
        print(f"Scan complete. Found: {matches if matches else 'No match'}")
        # 15 min baad fir scan karega
        time.sleep(900)

@app.route('/')
def home():
    return "Bot Running OK - Vol 1.5x filter active"

if __name__ == "__main__":
    # Scanner ko background me chalao
    threading.Thread(target=main_loop, daemon=True).start()
    # Flask server - isse 'Application exited early' fix hoga
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
