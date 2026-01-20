import yfinance as yf
import pandas_ta as ta
import asyncio
import os
import requests
from telegram import Bot
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier
from flask import Flask
from threading import Thread
from textblob import TextBlob
import pytz
import holidays
from supabase import create_client, Client
import warnings

warnings.filterwarnings("ignore")

# --- CONFIGURACIÓN ---
TOKEN = os.getenv('telegram_token')
CHAT_ID = os.getenv('chat_ID')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
FMP_API_KEY = os.getenv('fmp_api_key')

bot = Bot(token=TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ACTIVOS ORIGINALES
CRYPTO_ACTIVOS = [
    ("BTC-USD", "Bitcoin"), ("ETH-USD", "Ethereum"), ("BNB-USD", "Binance Coin"),
    ("ADA-USD", "Cardano"), ("SOL-USD", "Solana"), ("LINK-USD", "Chainlink"),
    ("AAVE-USD", "Aave"), ("MKR-USD", "MakerDAO"), ("COMP-USD", "Compound"), ("SNX-USD", "Synthetix")
]
COMMODITIES_ACTIVOS = [
    ("GC=F", "Oro"), ("SI=F", "Plata"), ("HG=F", "Cobre"),
    ("CL=F", "Petróleo Crudo"), ("NG=F", "Gas Natural"), ("PA=F", "Paladio")
]
COLOMBIAN_ACTIVOS = [("EC", "Ecopetrol")] # Quitamos ISA temporalmente por error 'delisted'

def obtener_sentimiento(ticker):
    if not FMP_API_KEY: return 0
    try:
        url = f"https://financialmodelingprep.com/api/v3/stock_news?tickers={ticker}&limit=3&apikey={FMP_API_KEY}"
        res = requests.get(url, timeout=5).json()
        if not res or not isinstance(res, list): return 0
        return (sum(TextBlob(n.get('title', '')).sentiment.polarity for n in res) / 3) * 0.1
    except: return 0

async def procesar_activo(ticker, nombre, umbral=0.70):
    try:
        # Descarga de datos
        df = yf.download(ticker, period='10d', interval='60m', progress=False)
        if df.empty or len(df) < 25: return

        df['RSI'] = ta.rsi(df['Close'], length=14)
        df['Target'] = (df['Close'].shift(-1) > df['Close']).astype(int)
        df = df.dropna()

        X = df[['Close', 'RSI']].tail(20)
        y = df['Target'].tail(20)
        
        model = RandomForestClassifier(n_estimators=50, random_state=42)
        model.fit(X[:-1], y[:-1])
        
        prob_base = model.predict_proba(X.tail(1))[:, 1][0]
        prob_final = prob_base + obtener_sentimiento(ticker)

        if prob_final >= umbral:
            precio = float(df['Close'].iloc[-1])
            
            # Guardar en Supabase (Solo inserción para evitar error JSON)
            try:
                supabase.table("señales").insert({
                    "ticker": ticker, 
                    "precio_entrada": precio, 
                    "probabilidad": float(prob_final)
                }).execute()
            except: pass
            
            msg = (f"🚨 **SEÑAL 70%**\n"
                   f"Activo: `{nombre}`\n"
                   f"Probabilidad: {prob_final:.1%}\n"
                   f"Precio: ${precio:.2f}")
            await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')
    except Exception as e:
        print(f"Error en {ticker}: {e}")

async def main_loop():
    while True:
        print("Iniciando nuevo escaneo...")
        for t, n in CRYPTO_ACTIVOS + COMMODITIES_ACTIVOS + COLOMBIAN_ACTIVOS:
            await procesar_activo(t, n)
            await asyncio.sleep(15) # Evita el Rate Limit de Yahoo Finance

        await bot.send_message(chat_id=CHAT_ID, text="✅ Ciclo completado. Esperando 1 hora.")
        await asyncio.sleep(3600)

app = Flask('')
@app.route('/')
def home(): return "INVESTFRED LIVE"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

if __name__ == "__main__":
    Thread(target=run_flask).start()
    asyncio.run(main_loop())

