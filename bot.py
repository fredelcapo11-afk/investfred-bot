import yfinance as yf
import pandas_ta as ta
import asyncio
import os
import requests
import matplotlib.pyplot as plt
import io
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

# 1. TUS ACTIVOS FIJOS (Los que tenías originalmente)
ACTIVOS_FIJOS = [
    ("BTC-USD", "Bitcoin"), ("ETH-USD", "Ethereum"), ("SOL-USD", "Solana"),
    ("NEAR-USD", "NEAR Protocol"), ("RIO-USD", "Realio Network"),
    ("GC=F", "Oro"), ("SI=F", "Plata"), ("CL=F", "Petróleo")
]

# Función para encontrar Penny Stocks dinámicamente de la plataforma FMP
def obtener_pennystocks_dinamicas():
    if not FMP_API_KEY: return []
    try:
        # Filtro: Precio < $10, Volumen > 1M, Top 7 más activas
        url = f"https://financialmodelingprep.com/api/v3/stock_screener?priceLowerThan=10&volumeMoreThan=1000000&exchange=NASDAQ,NYSE&limit=7&apikey={FMP_API_KEY}"
        res = requests.get(url, timeout=10).json()
        return [(item['symbol'], item['companyName']) for item in res]
    except:
        return []

def obtener_sentimiento(ticker):
    if not FMP_API_KEY: return 0
    try:
        url = f"https://financialmodelingprep.com/api/v3/stock_news?tickers={ticker}&limit=3&apikey={FMP_API_KEY}"
        res = requests.get(url, timeout=5).json()
        if not res or not isinstance(res, list): return 0
        return (sum(TextBlob(n.get('title', '')).sentiment.polarity for n in res) / 3) * 0.1
    except: return 0

async def procesar_activo(ticker, nombre, umbral=0.60):
    try:
        # Descarga de datos (Velas de 15m para equilibrio entre Cripto y Pennys)
        df = yf.download(ticker, period='3d', interval='15m', progress=False)
        if df.empty or len(df) < 30: return "⚠️ Sin datos"

        # Indicadores
        df['RSI'] = ta.rsi(df['Close'], length=14)
        df['Vol_Avg'] = df['Volume'].rolling(window=20).mean()
        bbands = ta.bbands(df['Close'], length=20, std=2)
        df['BBU'] = bbands['BBU_20_2.0']
        df['BBL'] = bbands['BBL_20_2.0']

        # Inteligencia Artificial
        df['Target'] = (df['Close'].shift(-1) > df['Close']).astype(int)
        df_ml = df.dropna()
        X = df_ml[['Close', 'RSI']].tail(30)
        y = df_ml['Target'].tail(30)
        
        model = RandomForestClassifier(n_estimators=50, random_state=42)
        model.fit(X[:-1], y[:-1])
        prob_final = model.predict_proba(X.tail(1))[:, 1][0] + obtener_sentimiento(ticker)

        # Lógica de detección
        ultimo_precio = df['Close'].iloc[-1]
        mult_vol = df['Volume'].iloc[-1] / df['Vol_Avg'].iloc[-1] if df['Vol_Avg'].iloc[-1] > 0 else 0
        es_breakout = (ultimo_precio > df['BBU'].iloc[-1] and mult_vol >= 1.5)

        if prob_final >= umbral or es_breakout:
            plt.style.use('dark_background')
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
            ax1.plot(df.index, df['Close'], color='#00ffcc', linewidth=2)
            ax1.fill_between(df.index, df['BBU'], df['BBL'], color='white', alpha=0.05)
            ax1.set_title(f"ANÁLISIS: {nombre} ({ticker})", fontsize=12)
            ax2.plot(df.index, df['RSI'], color='#ff007a')
            
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            plt.close()

            tipo = "🚀 BREAKOUT" if es_breakout else "🧠 IA SIGNAL"
            caption = (f"{tipo} | `{nombre}`\n\n"
                       f"💰 Precio: ${ultimo_precio:.2f}\n"
                       f"📊 RSI: {df['RSI'].iloc[-1]:.1f}\n"
                       f"🧠 Probabilidad: {prob_final:.1%}\n"
                       f"⚡ Vol: x{mult_vol:.1f}")
            
            await bot.send_photo(chat_id=CHAT_ID, photo=buf, caption=caption, parse_mode='Markdown')
            return f"✅ SEÑAL ({prob_final:.0%})"
        
        return "⚪ OK"
    except:
        return "❌ Error"

async def main_loop():
    while True:
        print("Iniciando ciclo híbrido...")
        
        # Combinamos tus fijos con los dinámicos del mercado
        dinamicos = obtener_pennystocks_dinamicas()
        todos = ACTIVOS_FIJOS + dinamicos
        
        resumen = []
        for t, n in todos:
            estado = await procesar_activo(t, n)
            resumen.append(f"• {t}: {estado}")
            await asyncio.sleep(5) 

        # Enviar resumen del ciclo
        msg = (f"📋 **RESUMEN CICLO HÍBRIDO**\n"
               f"Fijos analizados: {len(ACTIVOS_FIJOS)}\n"
               f"Penny Stocks encontradas: {len(dinamicos)}\n\n"
               + "\n".join(resumen))
        try:
            await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')
        except: pass

        print("Ciclo completado. Esperando 30 minutos...")
        await asyncio.sleep(1800)

# SERVIDOR PARA RENDER
app = Flask('')
@app.route('/')
def home(): return "INVESTFRED AI - MODO HÍBRIDO (FIJOS + PENNYS) ACTIVO"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

if __name__ == "__main__":
    Thread(target=run_flask).start()
    asyncio.run(main_loop())

