import yfinance as yf
import pandas as pd
import requests
from nsepython import nse_optionchain_scrapper

# --- TELEGRAM CONFIG ---
TELEGRAM_TOKEN = "8796819926:AAFWziABJAdsOZ-RO5XO3H7_waIpdrdb-xU"
CHAT_ID = "1133256294"

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

def calculate_plus_di(df, period=14):
    df = df.copy()
    df['H-pH'] = df['High'] - df['High'].shift(1)
    df['L-pL'] = df['Low'].shift(1) - df['Low']
    df['+DM'] = 0.0
    df.loc[(df['H-pH'] > df['L-pL']) & (df['H-pH'] > 0), '+DM'] = df['H-pH']
    df['TR'] = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift(1)).abs(), (df['Low']-df['Close'].shift(1)).abs()], axis=1).max(axis=1)
    df['TR14'] = df['TR'].ewm(alpha=1/period, adjust=False).mean()
    df['+DM14'] = df['+DM'].ewm(alpha=1/period, adjust=False).mean()
    df['+DI'] = 100 * (df['+DM14'] / df['TR14'])
    return df

def scan_full(symbol):
    yf_symbol = f"{symbol}.NS"
    try:
        # Daily Data
        daily = yf.download(yf_symbol, period="50d", interval="1d", progress=False, auto_adjust=True)
        if len(daily) < 25: return None
        daily = calculate_plus_di(daily)

        # 15m Data
        intraday = yf.download(yf_symbol, period="5d", interval="15m", progress=False, auto_adjust=True)
        if len(intraday) < 10: return None

        # --- CONDITION 1: Price ---
        latest_15m_close = float(intraday['Close'].iloc[-1])
        prev_day_high = float(daily['High'].iloc[-2])
        cond_price = latest_15m_close > prev_day_high

        # --- CONDITION 2: ADX +DI Cross 20 ---
        curr_di = float(daily['+DI'].iloc[-1])
        prev_di = float(daily['+DI'].iloc[-2])
        cond_di = (curr_di > 20 and prev_di <= 20)

        # --- CONDITION 3: VOLUME ---
        # Aaj ka Volume > 20 Day Average Volume ka 1.2x
        avg_vol_20 = float(daily['Volume'].iloc[-21:-1].mean())
        today_vol = float(daily['Volume'].iloc[-1])
        cond_volume = today_vol > (avg_vol_20 * 1.2)

        # --- CONDITION 4: OI ---
        # NSE se OI nikalo
        cond_oi = False
        oi_data_text = "N/A"
        try:
            chain = nse_optionchain_scrapper(symbol)
            # ATM ke aas paas ka CE OI check
            spot = chain['records']['underlyingValue']
            atm_strike = round(spot / 50) * 50
            
            # us strike ka CE data dhoondo
            for item in chain['records']['data']:
                if item['strikePrice'] == atm_strike and 'CE' in item:
                    ce_oi = item['CE']['openInterest']
                    ce_oi_change = item['CE']['changeinOpenInterest']
                    ce_oi_change_per = item['CE']['pChangeinOpenInterest']
                    
                    # OI badh raha hai + Price badh raha hai = Long Buildup (Best)
                    if ce_oi_change > 0 and ce_oi_change_per > 5:
                        cond_oi = True
                        oi_data_text = f"OI {ce_oi} (+{ce_oi_change_per:.1f}%) Long Buildup"
                    break
        except:
            # Agar NSE API fail ho to OI condition ko skip kar do (sirf 3 condition se kaam chalega)
            cond_oi = True 
            oi_data_text = "OI API Skip"

        # --- FINAL CHECK ---
        if cond_price and cond_di and cond_volume and cond_oi:
            return {
                "stock": symbol,
                "close": latest_15m_close,
                "prev_high": prev_day_high,
                "di": f"{prev_di:.1f}->{curr_di:.1f}",
                "vol": f"{today_vol/100000:.1f}L vs Avg {avg_vol_20/100000:.1f}L",
                "oi": oi_data_text,
                "strike": round(latest_15m_close / 50) * 50
            }
        return None
    except Exception as e:
        print(f"{symbol} Error: {e}")
        return None

# --- SCAN ---
NIFTY_100 = ["RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK","SBIN","BHARTIARTL","ITC","LT","BAJFINANCE","MARUTI","TITAN","SUNPHARMA","ONGC"]

send_telegram("🚀 <b>Full Scanner ON</b> - Price + ADX + Volume + OI")

for stock in NIFTY_100:
    res = scan_full(stock)
    if res:
        msg = f"""
🔥 <b>STRONG BREAKOUT - {res['stock']}</b>

✅ 1. 15m Close {res['close']} > Prev High {res['prev_high']}
✅ 2. ADX +DI Cross 20: {res['di']}
✅ 3. Volume: {res['vol']} (High Volume)
✅ 4. OI: {res['oi']} (Long Buildup)

👉 <b>BUY {res['stock']} {res['strike']} CE</b>
👉 SL: Prev Day High

#NSE #Breakout
"""
        send_telegram(msg)
        print(f"ALERT: {res['stock']}")
    else:
        print(f"Skip: {stock}")
