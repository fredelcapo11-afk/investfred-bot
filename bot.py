import os
import io
import asyncio
import requests
import pandas as pd
import pandas_ta as ta
import matplotlib.pyplot as plt
from datetime import datetime
from flask import Flask
from threading import Thread
from telegram import Bot
from textblob import TextBlob
from sklearn.ensemble import RandomForestClassifier
import warnings

# Ignorar avisos de devaluació
warnings.filterwarnings("ignore")

# --- CONFIGURACIÓ DE VARIABLES D'ENTORN ---
TOKEN = os.getenv('telegram_token')
CHAT_ID = os.getenv('chat_ID')
FMP_API_KEY = os.getenv('fmp_api_key')
ALPHA_KEY = os.getenv('ALPHA_VANTAGE_KEY')

bot = Bot(token=TOKEN)

# Actius principals
ACTIVOS_FIJOS = [
    ("BTC-USD", "Cripto"), 
    ("ETH-USD", "Cripto"), 
    ("SOL-USD", "Cripto"),
    ("GC=F", "Or"), 
    ("CL=F", "Petroli")
]

# --- FUNCIONS D'ANÀLISI ---

def obtener_pennystocks_dinamicas():
    if not FMP_API_KEY: return []
    try:
        url = f"https://financialmodelingprep.com/api/v3/stock_screener?priceLowerThan=10&volumeMoreThan=1000000&exchange=NASDAQ,NYSE&limit=5&apikey={FMP_API_KEY}"
        res = requests.get(url, timeout=10).json()
        return [(item['symbol'], "Penny Stock") for item in res]
    except: return []

def obtener_sentimiento(ticker):
    if not FMP_API_KEY: return 0
    try:
        symbol = ticker.split('-')[0]
        url = f"https://financialmodelingprep.com/api/v3/stock_news?tickers={symbol}&limit=3&apikey={FMP_API_KEY}"
        res = requests.get(url, timeout=5).json()
        if not res or not isinstance(res, list): return 0
        return (sum(TextBlob(n.get('title', '')).sentiment.polarity for n in res) / 3) * 0.1
    except: return 0

# --- GENERACIÓ DE GRÀFICS I SEÑALS ---

async def generar_y_enviar_grafico(df, ticker, nombre, prob_final, mult_vol, es_breakout):
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
    
    # Panel 1: Preu + Bollinger
    ax1.plot(df.index, df['Close'], color='#0052FF', linewidth=1.5, label='Preu')
    ax1.plot(df.index, df['BBU'], color='gray', linestyle='--', alpha=0.3, label='Bollinger Sup')
    ax1.plot(df.index, df['BBL'], color='gray', linestyle='--', alpha=0.3, label='Bollinger Inf')
    ax1.fill_between(df.index, df['BBU'], df['BBL'], color='gray', alpha=0.05)
    ax1.set_title(f"AI Signal: {ticker} ({nombre}) - Prob: {prob_final:.1%}", fontsize=12, fontweight='bold')
    ax1.legend(loc='upper left')

    # Panel 2: RSI
    ax2.plot(df.index, df['RSI'], color='#8A2BE2', linewidth=1.2, label='RSI')
    ax2.axhline(70, color='#FF4B4B', linestyle='--', alpha=0.6)
    ax2.axhline(30, color='#00C805', linestyle='--', alpha=0.6)
    ax2.fill_between(df.index, 70, 100, color='#FF4B4B', alpha=0.05)
    ax2.fill_between(df.index, 0, 30, color='#00C805', alpha=0.05)
    ax2.set_ylim(0, 100)
    ax2.legend(loc='upper right')

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150)
    buf.seek(0)
    plt.close()

    tipo = "🚀 BREAKOUT DETECTAT" if es_breakout else "🧠 IA + SENTIMENT SIGNAL"
    ballena = f"\nFlujo de Órdenes: ⚠️ BALENA DETECTADA (Vol x{mult_vol:.1f})" if mult_vol >= 3.0 else f"\nFlujo de Órdenes: Vol x{mult_vol:.1f}"
    
    caption = (f"{tipo}\n"
               f"Actiu: `{ticker}` | Sector: {nombre}\n"
               f"Preu: `${df['Close'].iloc[-1]:.2f}`\n"
               f"Probabilitat IA: `{prob_final:.1%}`"
               f"{ballena}")
    
    await bot.send_photo(chat_id=CHAT_ID, photo=buf, caption=caption, parse_mode='Markdown')

# --- PROCESSAMENT AMB ALPHA VANTAGE ---

async def procesar_activo(ticker, nombre, umbral=0.60):
    try:
        symbol = ticker.split('-')[0]
        if "-USD" in ticker:
            url = f"https://www.alphavantage.co/query?function=CRYPTO_INTRADAY&symbol={symbol}&market=USD&interval=15min&outputsize=small&apikey={ALPHA_KEY}"
        else:
            url = f"https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol={ticker}&interval=15min&outputsize=small&apikey={ALPHA_KEY}"
        
        data = requests.get(url, timeout=15).json()
        
        if "Note" in data: return "⏳ Limit API"
        
        ts_key = next(k for k in data.keys() if "Time Series" in k)
        df = pd.DataFrame.from_dict(data[ts_key], orient='index').astype(float)
        df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()

        # Indicadors tècnics
        df['RSI'] = ta.rsi(df['Close'], length=14)
        bb = ta.bbands(df['Close'], length=20, std=2)
        df['BBU'], df['BBL'] = bb['BBU_20_2.0'], bb['BBL_20_2.0']
        df['Vol_Avg'] = df['Volume'].rolling(window=20).mean()

        # IA - RandomForest
        df_ml = df.dropna().tail(31)
        if len(df_ml) < 20: return "⚠️ Poces dades"
        
        X = df_ml[['Close', 'RSI']].iloc[:-1]
        y = (df_ml['Close'].shift(-1) > df_ml['Close']).astype(int).iloc[:-1]
        
        model = RandomForestClassifier(n_estimators=50, random_state=42)
        model.fit(X, y)
        prob_final = model.predict_proba(df_ml[['Close', 'RSI']].tail(1))[:, 1][0] + obtener_sentimiento(ticker)

        # Lògica de Breakout i Balenes
        ultimo_precio = df['Close'].iloc[-1]
        mult_vol = df['Volume'].iloc[-1] / df['Vol_Avg'].iloc[-1] if df['Vol_Avg'].iloc[-1] > 0 else 0
        es_breakout = (ultimo_precio > df['BBU'].iloc[-1] and mult_vol >= 1.5)

        if prob_final >= umbral or es_breakout:
            await generar_y_enviar_grafico(df, ticker, nombre, prob_final, mult_vol, es_breakout)
            return "✅ SEÑAL"
        
        return "⚪ OK"
    except Exception as e:
        print(f"Error en {ticker}: {e}")
        return "❌ Error"

# --- BUCLE PRINCIPAL I SERVIDOR ---

async def main_loop():
    while True:
        ahora = datetime.now()
        # Horaris d'alta volatilitat (apertura, migdia i tancament)
        if ahora.hour in [9, 13, 16]:
            print(f"[{ahora}] Iniciant cicle de mercat...")
            dinamicos = obtener_pennystocks_dinamicas()
            todos = ACTIVOS_FIJOS + dinamicos
            for t, n in todos:
                await procesar_activo(t, n)
                await asyncio.sleep(15) # Evitar ban de la API
            await asyncio.sleep(3600) # Esperar 1 hora per no repetir el cicle
        await asyncio.sleep(60)

app = Flask('')
@app.route('/')
def home(): return "INVESTFRED AI - ALPHA VANTAGE MODE ONLINE"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

if __name__ == "__main__":
    Thread(target=run_flask).start()
    print("Bot iniciat. Esperant horaris de mercat...")
    asyncio.run(main_loop())
