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
from supabase import create_client, Client

# --- CONFIGURACIÓN ---
TOKEN = os.getenv('telegram_token')
CHAT_ID = os.getenv('chat_ID')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

bot = Bot(token=TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# TUS ACTIVOS ORIGINALES
CRYPTO_ACTIVOS = [
    ("BTC-USD", "Bitcoin"), ("ETH-USD", "Ethereum"), ("BNB-USD", "Binance Coin"),
    ("ADA-USD", "Cardano"), ("SOL-USD", "Solana"), ("LINK-USD", "Chainlink"),
    ("AAVE-USD", "Aave"), ("MKR-USD", "MakerDAO"), ("COMP-USD", "Compound"), ("SNX-USD", "Synthetix")
]
COMMODITIES_ACTIVOS = [("GC=F", "Oro"), ("SI=F", "Plata"), ("CL=F", "Petróleo")]

async def procesar_activo(ticker, nombre):
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
        
        prob_final = model.predict_proba(X.tail(1))[:, 1][0]

        # LÓGICA 70%
        if prob_final >= 0.70:
            precio = float(df['Close'].iloc[-1])
            
            # GUARDAR EN DB (Solo inserción para evitar error JSON)
            try:
                supabase.table("señales").insert({
                    "ticker": ticker, "precio_entrada": precio, "probabilidad": float(prob_final)
                }).execute()
            except: pass
            
            await bot.send_message(chat_id=CHAT_ID, text=f"🚨 **SEÑAL 70%**\nActivo: {nombre}\nProb: {prob_final:.1%}\nPrecio: ${precio:.2f}", parse_mode='Markdown')
    except Exception as e:
        print(f"Error en {ticker}: {e}")

async def main_loop():
    while True:
        print("Iniciando escaneo...")
        for t, n in CRYPTO_ACTIVOS + COMMODITIES_ACTIVOS:
            await procesar_activo(t, n)
            await asyncio.sleep(15) # Pausa para evitar Rate Limit Error

        await bot.send_message(chat_id=CHAT_ID, text="✅ Ciclo completado. Esperando 1 hora.")
        await asyncio.sleep(3600)

app = Flask('')
@app.route('/')
def home(): return "BOT ACTIVE"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

if __name__ == "__main__":
    Thread(target=run_flask).start()
    asyncio.run(main_loop())
