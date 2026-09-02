import yfinance as yf, requests, math, pandas as pd
from scipy.stats import norm
from datetime import datetime
import os, random
BOT_TOKEN = os.getenv("8796819926:AAFWziABJAdsOZ-RO5XO3H7_waIpdrdb-xU")
CHAT_ID = os.getenv("1133256294")
def get_fno_stocks():
    try:
        url = "https://www.nseindia.com/api/equity-stockIndices?index=SECURITIES%20IN%20F%26O"
        sess = requests.Session()
        sess.headers.update({"User-Agent": "Mozilla/5.0"})
        sess.get("https://www.nseindia.com", timeout=5)
        data = sess.get(url, timeout=10).json()
        return [item['symbol'] for item in data['data']]
    except: return ["RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK","SBIN","BHARTIARTL","LT","ITC","TATAMOTORS"]
def get_delta(S,K,T,iv):
    try:
        d1 = (math.log(S/K) + (0.06 + 0.5*iv**2)*T) / (iv*math.sqrt(T))
        return norm.cdf(d1)
    except: return 0.5
def get_chain(symbol):
    try:
        path = "indices" if symbol in ["NIFTY","BANKNIFTY"] else "equities"
        url = f"https://www.nseindia.com/api/option-chain-{path}?symbol={symbol}"
        sess = requests.Session()
        sess.headers.update({"User-Agent": "Mozilla/5.0"})
        sess.get("https://www.nseindia.com", timeout=5)
        return sess.get(url, timeout=10).json()
    except: return None
def get_atr_ema_vwap(ticker, interval):
    try:
        df = yf.download(ticker, period='10d', interval=interval, progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        if df.empty or len(df) < 20: return None
        df['H-L'] = df['High'] - df['Low']
        df['H-C'] = abs(df['High'] - df['Close'].shift(1))
        df['L-C'] = abs(df['Low'] - df['Close'].shift(1))
        df['TR'] = df[['H-L','H-C','L-C']].max(axis=1)
        df['ATR'] = df['TR'].rolling(14).mean()
        df['EMA9'] = df['Close'].ewm(span=9).mean()
        df['VWAP'] = (df['Close']*df['Volume']).cumsum() / df['Volume'].cumsum()
        return df.iloc[-1]
    except: return None
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except: pass
now=datetime.now()
all_signals=[]
try:
    vix_df = yf.download("^INDIAVIX", period='2d', interval='1d', progress=False, auto_adjust=True)
    if isinstance(vix_df.columns, pd.MultiIndex): vix_df.columns = vix_df.columns.get_level_values(0)
    vix_val = float(vix_df['Close'].iloc[-1])
except: vix_val=15
if 14 <= vix_val <= 20:
    FNO_LIST=get_fno_stocks()
    random.shuffle(FNO_LIST)
    SCAN_LIST=["NIFTY","BANKNIFTY"]+FNO_LIST[:30]
    for symbol in SCAN_LIST:
        yt="^NSEI" if symbol=="NIFTY" else "^NSEBANK" if symbol=="BANKNIFTY" else f"{symbol}.NS"
        last_15m=get_atr_ema_vwap(yt,"15m")
        last_1h=get_atr_ema_vwap(yt,"60m")
        last_5m=get_atr_ema_vwap(yt,"5m")
        if last_15m is None or last_1h is None or last_5m is None: continue
        if not (last_5m['Close'] > last_5m['EMA9'] and last_5m['Close'] > last_5m['VWAP']): continue
        chain=get_chain(symbol)
        if not chain: continue
        try:
            spot=chain['records']['underlyingValue']
            expiry=chain['records']['expiryDates'][0]
            T=max((datetime.strptime(expiry,"%d-%b-%Y")-now).days/365,0.01)
        except: continue
        atr_15m=float(last_15m['ATR'])
        atr_1h=float(last_1h['ATR'])
        for item in chain['records']['data']:
            if 'CE' not in item: continue
            ce=item['CE']
            k,ltp=ce['strikePrice'],ce['lastPrice']
            vol,oi_pct=ce.get('totalTradedVolume',0),ce.get('pChangeinOpenInterest',0)
            if symbol in ["NIFTY","BANKNIFTY"]:
                if abs(k-spot) > spot*0.015: continue
                if vol < 100000: continue
            else:
                if abs(k-spot) > spot*0.03: continue
                if vol < 40000: continue
            if oi_pct < 15: continue
            iv=ce.get('impliedVolatility',25)/100 or 0.25
            delta=get_delta(spot,k,T,iv)
            if delta < 0.40: continue
            intrinsic=max(0,spot-k)
            tv_pct=((ltp-intrinsic)/ltp*100) if ltp>0 else 100
            if tv_pct >= 45: continue
            buy=round(ltp + (atr_15m * delta * 0.15),2)
            tgt=round(buy + (atr_1h * delta * 0.50),2)
            sl=round(buy - (atr_15m * delta * 0.30),2)
            score=(oi_pct*2)+(vol/10000)+(delta*100)-tv_pct
            all_signals.append({"symbol":symbol,"strike":k,"spot":spot,"buy":buy,"tgt":tgt,"sl":sl,"delta":round(delta,2),"tv":round(tv_pct,1),"oi":oi_pct,"vol":vol,"score":score,"vix":round(vix_val,1)})
            break
    if all_signals:
        all_signals=sorted(all_signals,key=lambda x:x['score'],reverse=True)
        top2=all_signals[:2]
        for s in top2:
            tag="INDEX" if s['symbol'] in ["NIFTY","BANKNIFTY"] else "STOCK"
            text=(f"🔥 *TOP {top2.index(s)+1} | {tag}: {s['symbol']} {s['strike']} CE*\nSpot:{s['spot']} | VIX:{s['vix']} | Score:{int(s['score'])}\nBUY:`{s['buy']}`\nTGT:`{s['tgt']}`\nSL:`{s['sl']}`\nΔ:{s['delta']} TV:{s['tv']}% OI:{s['oi']}% Vol:{s['vol']}")
            send_telegram(text)
