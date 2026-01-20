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
import warnings

warnings.filterwarnings("ignore")

# --- CONFIGURACIÓN ---
TOKEN = os.getenv('telegram_token')
CHAT_ID = os.getenv('chat_ID')
FMP_API_KEY = os.getenv('fmp_api_key')

bot = Bot(token=TOKEN)

# TUS ACTIVOS ORIGINALES
CRYPTO_ACTIVOS = [
    ("BTC-USD", "Bitcoin"), ("ETH-USD", "Ethereum"), ("BNB-USD", "Binance Coin"),
    ("ADA-USD", "Cardano"), ("SOL-USD", "Solana"), ("LINK-USD", "Chainlink"),
    ("AAVE-USD", "Aave"), ("MKR-USD", "MakerDAO"), ("COMP-USD", "Compound"), ("SNX-USD", "Synthetix")
]
COMMODITIES_ACTIVOS = [
    ("GC=F", "Oro"), ("SI=F", "Plata"), ("HG=F", "Cobre"),
    ("CL=F", "Petróleo Crudo"), ("NG=F", "Gas Natural"), ("PA=F", "Paladio")
]

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
        df = yf.download(ticker, period='12d', interval='60m', progress=False)
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

        # LÓGICA DEL 70%
        if prob_final >= umbral:
            precio = float(df['Close'].iloc[-1])
            msg = (f"🚨 **SEÑAL 70% DETECTADA**\n"
                   f"Activo: `{nombre}` ({ticker})\n"
                   f"Probabilidad: {prob_final:.1%}\n"
                   f"Precio Actual: ${precio:.2f}")
            await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')
            print(f"Señal enviada para {ticker}")
            
    except Exception as e:
        print(f"Error procesando {ticker}: {e}")

async def main_loop():
    while True:
        print(f"Iniciando escaneo: {datetime.now()}")
        
        # Combinamos tus activos
        todos_los_activos = CRYPTO_ACTIVOS + COMMODITIES_ACTIVOS
        
        for t, n in todos_los_activos:
            await procesar_activo(t, n)
            # Pausa de 15 seg para evitar el error de "Too Many Requests"
            await asyncio.sleep(15) 

        # Mensaje de vida del bot
        try:
            await bot.send_message(chat_id=CHAT_ID, text="✅ Ciclo completado con éxito. Próximo escaneo en 1 hora.")
        except: pass

        print("Esperando 1 hora para el siguiente ciclo...")
        await asyncio.sleep(3600)

# Servidor Flask básico para Render
app = Flask('')
@app.route('/')
def home(): return "INVESTFRED AI - SIN BASE DE DATOS - ACTIVO"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

if __name__ == "__main__":
    # Iniciar servidor web en segundo plano
    Thread(target=run_flask).start()
    # Iniciar el bucle del bot
    asyncio.run(main_loop())
