import yfinance as yf
import pandas_ta as ta
import asyncio
import pandas as pd
import os
import requests
import matplotlib.pyplot as plt
import io
import time
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
FMP_API_KEY = os.getenv('fmp_api_key') # Agrégala a Environment en Render
bot = Bot(token=TOKEN)

# --- SERVIDOR WEB PARA ESTABILIDAD EN RENDER ---
app = Flask('')
@app.route('/')
def home(): return "INVESTFRED AI is running!"

def run_web():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# --- ANÁLISIS DE SENTIMIENTO REAL ---
def obtener_sentimiento(ticker):
    try:
        url = f"https://financialmodelingprep.com/api/v3/stock_news?tickers={ticker}&limit=5&apikey={FMP_API_KEY}"
        response = requests.get(url)
        news = response.json()
        if not news: return 0
        
        # Analiza el título de las noticias
        sentiment_score = 0
        for item in news:
            analysis = TextBlob(item['title'])
            sentiment_score += analysis.sentiment.polarity
        return (sentiment_score / len(news)) * 0.1 # Impacto moderado en la probabilidad
    except:
        return 0

# --- MOTOR DE MACHINE LEARNING + GRÁFICO ---
def analizar_y_graficar(df, ticker, sector, prob):
    try:
        # Generar gráfico similar al bot anterior
        plt.figure(figsize=(10, 6))
        plt.subplot(2, 1, 1)
        plt.plot(df.index, df['Close'], color='blue', label='Precio')
        plt.title(f"AI Signal: {ticker} ({sector}) - Prob: {prob:.1%}")
        plt.grid(True)
        
        plt.subplot(2, 1, 2)
        rsi = ta.rsi(df['Close'], length=14)
        plt.plot(df.index, rsi, color='purple', label='RSI')
        plt.axhline(70, color='red', linestyle='--', alpha=0.5)
        plt.axhline(30, color='green', linestyle='--', alpha=0.5)
        plt.grid(True)
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        return buf
    except:
        return None

def predecir_tendencia(df, ticker):
    try:
        data = df.copy()
        data['Target'] = (data['Close'].shift(-1) > data['Close']).astype(int)
        data['RSI'] = ta.rsi(data['Close'], length=14)
        data['Vol_Rel'] = data['Volume'] / data['Volume'].rolling(20).mean()
        data = data.dropna()
        
        if len(data) < 30: return 0.5
        
        X = data[['RSI', 'Vol_Rel']]
        y = data['Target']
        model = RandomForestClassifier(n_estimators=100, random_state=42)
        model.fit(X[:-1], y[:-1])
        
        prob_base = model.predict_proba(X.tail(1))[0][1]
        sentimiento = obtener_sentimiento(ticker)
        return prob_base + sentimiento
    except: return 0.5

async def procesar_activo(ticker, sector):
    print(f"🔍 Analizando ahora: {ticker} ({sector})...")
    try:
        # Cambiamos a intervalo de 1 hora para Penny Stocks (más sensible)
        df = yf.download(ticker, period="1mo", interval="60m", progress=False)
        if df is None or df.empty: return
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        prob = predecir_tendencia(df, ticker)
        
        # Cálculo de anomalía de volumen (Detecta ballenas)
        vol_actual = df['Volume'].iloc[-1]
        vol_promedio = df['Volume'].rolling(20).mean().iloc[-1]
        vol_relativo = vol_actual / vol_promedio
        
        if prob > 0.05:
            precio = float(df['Close'].iloc[-1])
            img = analizar_y_graficar(df, ticker, sector, prob)
            
            # Etiqueta de volumen para el mensaje
            nota_vol = "Normal"
            if vol_relativo > 3.0: nota_vol = "⚠️ BALLENA DETECTADA (Vol x3)"
            elif vol_relativo > 1.5: nota_vol = "Pico de Interés (Vol x1.5)"
            
            msg = (f"🧠 **IA + SENTIMENT SIGNAL**\n"
                   f"Activo: `{ticker}` | Sector: {sector}\n"
                   f"Precio: ${precio:.2f}\n"
                   f"Probabilidad IA: {prob:.1%}\n"
                   f"Flujo de Órdenes: `{nota_vol}`")
            
            if img:
                await bot.send_photo(chat_id=CHAT_ID, photo=img, caption=msg, parse_mode='Markdown')
            
            
            if img:
                await bot.send_photo(chat_id=CHAT_ID, photo=img, caption=msg, parse_mode='Markdown')
            else:
                await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')
    except Exception as e:
        print(f"Error en {ticker}: {e}")

async def main_loop():
    print("🚀 INVESTFRED AI v14.0: Iniciando ciclo estable...")
    while True:
        try:
            # Búsqueda en FMP (Penny Stocks)
            url_fmp = f"https://financialmodelingprep.com/api/v3/stock_screener?priceLowerThan=5&volumeMoreThan=1000000&limit=10&apikey={FMP_API_KEY}"
            data_fmp = requests.get(url_fmp).json()
            activos = [(item['symbol'], item.get('sector', 'Penny Stock')) for item in data_fmp]
            
            # Activos Globales
            globales = [("BTC-USD", "Cripto"), 
                ("ETH-USD", "Cripto"), 
                ("ADA-USD", "Cripto"),
                ("NEAR-USD", "Cripto"),
                ("RIO-USD", "Cripto"),
                ("GC=F", "Oro"),
                ("SI=F", "Plata"),
                ("HG=F", "Cobre"),
                ("CL=F", "Petroleo Crudo")]
            
            for t, s in activos + globales:
                await procesar_activo(t, s)
                await asyncio.sleep(5) # Evita bloqueos de Yahoo
            
            print("✅ Ciclo completado. Esperando 1 hora...")
            await asyncio.sleep(3600)
        except Exception as e:
            print(f"Error: {e}")
            await asyncio.sleep(300)

# --- FUNCIÓN PARA DESCARGAR EL LOG DESDE TELEGRAM ---
@app.route('/download')
def download_log():
    try:
        if os.path.exists(ARCHIVO_LOG):
            with open(ARCHIVO_LOG, 'rb') as f:
                # El bot te envía el archivo automáticamente cuando alguien visita la URL/download
                # O puedes activarlo con un comando si prefieres
                return "Archivo listo para envío"
        return "No hay registros aún"
    except: return "Error al descargar"

# --- COMANDO DE TELEGRAM PARA RECIBIR EL EXCEL ---
# Añade esto dentro de tu lógica de mensajes si quieres solicitarlo por chat
async def enviar_backtesting():
    if os.path.exists(ARCHIVO_LOG):
        with open(ARCHIVO_LOG, 'rb') as doc:
            await bot.send_document(chat_id=CHAT_ID, document=doc, 
                                    caption="📊 Aquí tienes el reporte de Backtesting actualizado.")
    else:
        await bot.send_message(chat_id=CHAT_ID, text="❌ Aún no hay señales registradas.")

if __name__ == "__main__":
    # Iniciar servidor web para que Render vea el puerto 8080
    Thread(target=run_web).start()
    # Iniciar bot asíncrono
    asyncio.run(main_loop())






