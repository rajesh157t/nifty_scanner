import yfinance as yf
import pandas as pd
import numpy as np
from nsepython import nse_optionchain_scrapper, nse_fno
from datetime import datetime
import requests
import time

# ========== CONFIG ==========
TELEGRAM_BOT_TOKEN = "8796819926:AAFWziABJAdsOZ-RO5XO3H7_waIpdrdb-xU" 
TELEGRAM_CHAT_ID = "1133256294"
FNO_LIST = ["TITAN","ADANIPORTS","RELIANCE","COALINDIA","NTPC","ONGC","BAJFINANCE","LT","SUNPHARMA","POWERGRID"]

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=data, timeout=10)
    except:
        pass

def trix(df, period=14):
    close = df['Close']
    e1 = close.ewm(span=period).mean()
    e2 = e1.ewm(span=period).mean()
    e3 = e2.ewm(span=period).mean()
    return (e3 - e3.shift(1)) / e3.shift(1) * 100

def get_live_data(symbol):
    try:
        # Daily & Weekly
        d = yf.download(f"{symbol}.NS", period="6mo", interval="1d", progress=False, auto_adjust=True)
        w = yf.download(f"{symbol}.NS", period="1y", interval="1wk", progress=False, auto_adjust=True)
        if len(d) < 50: return None

        # Option Chain for OI + Delta (approx from chain)
        chain = nse_optionchain_scrapper(symbol)
        spot = chain['records']['underlyingValue']
        # nearest expiry = Sep expiry
        expiry = chain['records']['expiryDates'][0]

        # Find ATM CE with Delta ~0.4-0.6
        ce_data = None
        for item in chain['records']['data']:
            if item.get('expiryDate') == expiry and 'CE' in item:
                if abs(item['strikePrice'] - spot) < 150: # ATM ke aas paas
                    ce = item['CE']
                    # NSE gives delta indirectly via greeks if available, else we use 0.5 for ATM
                    # Filter: Delta > 40
                    delta = ce.get('delta', 50) # fallback
                    if ce.get('lastPrice',0) > 0:
                        ce_data = {
                            'strike': item['strikePrice'],
                            'ltp': ce['lastPrice'],
                            'oi': ce['openInterest'],
                            'oi_change': ce.get('changeinOpenInterest',0),
                            'volume': ce.get('totalTradedVolume',0),
                            'delta': ce.get('delta', 55) # agar greeks API me hai to
                        }
                        break

        if not ce_data: return None

        # Filters
        close = float(d['Close'].iloc[-1])
        vol_today = float(d['Volume'].iloc[-1])
        vol_avg = float(d['Volume'].iloc[-6:-1].mean())

        vol_rise = vol_today > vol_avg * 1.3
        price_rise = d['Close'].iloc[-1] > d['Close'].iloc[-2]
        long_buildup = price_rise and ce_data['oi_change'] > 0 and ce_data['volume'] > 1000

        swing = d['Low'].iloc[-1] > d['Low'].iloc[-2] > d['Low'].iloc[-3]

        trix_d = trix(d)
        trix_w = trix(w)
        trix_d_cross = trix_d.iloc[-2] < 0 and trix_d.iloc[-1] > 0
        trix_w_cross = trix_w.iloc[-2] < 0 and trix_w.iloc[-1] > 0

        delta_ok = ce_data['delta'] > 40

        if vol_rise and price_rise and long_buildup and swing and trix_d_cross and trix_w_cross and delta_ok:
            return {
                "SYMBOL": symbol,
                "SPOT": spot,
                "STRIKE": ce_data['strike'],
                "CE_LTP": ce_data['ltp'],
                "DELTA": ce_data['delta'],
                "OI_CHG%": round((ce_data['oi_change']/ce_data['oi']*100) if ce_data['oi'] else 0,2),
                "VOL_RATIO": round(vol_today/vol_avg,2),
                "EXPIRY": expiry
            }
    except Exception as e:
        print(f"{symbol} error {e}")
        return None

def main():
    final_list = []
    for sym in FNO_LIST:
        print(f"Checking {sym}...")
        res = get_live_data(sym)
        if res:
            final_list.append(res)
        time.sleep(1.5) # NSE block se bachne ke liye

    if final_list:
        df = pd.DataFrame(final_list)
        msg = f"🔥 *NSE Swing Buy Alert {datetime.now().date()}*\n\n"
        for r in final_list:
            msg += f"*{r['SYMBOL']}* {r['SPOT']} -> {r['STRIKE']}CE @ {r['CE_LTP']}\n"
            msg += f"Delta:{r['DELTA']} | Vol:{r['VOL_RATIO']}x | OI Chg:{r['OI_CHG%']}%\n"
            msg += f"TRIX D&W crossed 0 + Long Buildup ✅\n\n"
        print(df)
        send_telegram(msg)
        df.to_csv(f"alert_{datetime.now().date()}.csv", index=False)
    else:
        send_telegram("No stock matched today - TRIX/Delta filter fail")
        print("No match")

if __name__ == "__main__":
    main()
