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
FMP_API_KEY = os.getenv('fmp_api_key')
bot = Bot(token=TOKEN)

# --- SERVIDOR WEB PARA ESTABILIDAD EN RENDER ---
app = Flask('')
@app.route('/')
def home(): 
    return "INVESTFRED AI is running!"

def run_web():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)

# --- ANÁLISIS DE SENTIMIENTO REAL ---
def obtener_sentimiento(ticker):
    try:
        url = f"https://financialmodelingprep.com/api/v3/stock_news?tickers={ticker}&limit=5&apikey={FMP_API_KEY}"
        response = requests.get(url)
        news = response.json()
        if not news: 
            return 0
        
        sentiment_score = 0
        for item in news:
            analysis = TextBlob(item['title'])
            sentiment_score += analysis.sentiment.polarity
        return (sentiment_score / len(news)) * 0.1
    except:
        return 0

# --- MOTOR DE MACHINE LEARNING + GRÁFICO ---
def analizar_y_graficar(df, ticker, sector, prob):
    try:
        plt.figure(figsize=(10, 6))
        plt.subplot(2, 1, 1)
        plt.plot(df.index, df['Close'], color='blue', label='Precio')
        plt.title(f"AI Signal: {ticker} ({sector}) - Prob: {prob:.1%}")
        plt.grid(True)
        plt.legend()
        
        plt.subplot(2, 1, 2)
        rsi = ta.rsi(df['Close'], length=14)
        plt.plot(df.index, rsi, color='purple', label='RSI')
        plt.axhline(70, color='red', linestyle='--', alpha=0.5, label='Sobrecompra')
        plt.axhline(30, color='green', linestyle='--', alpha=0.5, label='Sobreventa')
        plt.grid(True)
        plt.legend()
        
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100)
        buf.seek(0)
        plt.close()
        return buf
    except Exception as e:
        print(f"Error generando gráfico para {ticker}: {e}")
        return None

def predecir_tendencia(df, ticker):
    try:
        data = df.copy()
        data['Target'] = (data['Close'].shift(-1) > data['Close']).astype(int)
        data['RSI'] = ta.rsi(data['Close'], length=14)
        data['Vol_Rel'] = data['Volume'] / data['Volume'].rolling(20).mean()
        data = data.dropna()
        
        if len(data) < 30: 
            return 0.5
        
        X = data[['RSI', 'Vol_Rel']]
        y = data['Target']
        model = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=5)
        model.fit(X[:-1], y[:-1])
        
        prob_base = model.predict_proba(X.tail(1))[0][1]
        sentimiento = obtener_sentimiento(ticker)
        return min(max(prob_base + sentimiento, 0), 1)  # Asegurar entre 0 y 1
    except Exception as e:
        print(f"Error en predicción para {ticker}: {e}")
        return 0.5

async def procesar_activo(ticker, sector):
    print(f"🔍 Analizando ahora: {ticker} ({sector})...")
    try:
        df = yf.download(ticker, period="1mo", interval="60m", progress=False, timeout=10)
        if df is None or df.empty or len(df) < 30:
            print(f"{ticker}: Datos insuficientes")
            return
            
        if isinstance(df.columns, pd.MultiIndex): 
            df.columns = df.columns.get_level_values(0)

        prob = predecir_tendencia(df, ticker)
        
        # Cálculo de anomalía de volumen
        vol_actual = df['Volume'].iloc[-1]
        vol_promedio = df['Volume'].rolling(20).mean().iloc[-1]
        vol_relativo = vol_actual / vol_promedio if vol_promedio > 0 else 1
        
        print(f"{ticker}: Probabilidad = {prob:.1%}, Vol Relativo = {vol_relativo:.2f}x")
        
        # AJUSTA ESTE UMBRAL PARA MÁS/MENOS SEÑALES
        if prob > 0.05:  # <-- Cambia este valor (0.05 = 5%)
            precio = float(df['Close'].iloc[-1])
            img = analizar_y_graficar(df, ticker, sector, prob)
            
            # Etiqueta de volumen
            nota_vol = "Normal"
            if vol_relativo > 3.0: 
                nota_vol = "⚠️ BALLENA DETECTADA (Vol x3)"
            elif vol_relativo > 1.5: 
                nota_vol = "Pico de Interés (Vol x1.5)"
            
            msg = (f"🧠 **IA + SENTIMENT SIGNAL**\n"
                   f"Activo: `{ticker}` | Sector: {sector}\n"
                   f"Precio: ${precio:.2f}\n"
                   f"Probabilidad IA: {prob:.1%}\n"
                   f"Flujo de Órdenes: `{nota_vol}`")
            
            if img:
                await bot.send_photo(chat_id=CHAT_ID, photo=img, caption=msg, parse_mode='Markdown')
            else:
                await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')
                
            print(f"✅ Señal enviada para {ticker}")
        else:
            print(f"❌ {ticker} no cumple criterios (prob={prob:.1%})")
            
    except Exception as e:
        print(f"Error en {ticker}: {e}")

async def main_loop():
    print("🚀 INVESTFRED AI v14.0: Iniciando ciclo estable...")
    print(f"Token configurado: {'Sí' if TOKEN else 'No'}")
    print(f"Chat ID configurado: {'Sí' if CHAT_ID else 'No'}")
    print(f"FMP API Key configurada: {'Sí' if FMP_API_KEY else 'No'}")
    
    while True:
        try:
            # Lista de activos globales (solo estos para pruebas)
            globales = [
                ("BTC-USD", "Cripto"), 
                ("ETH-USD", "Cripto"),
                ("AAPL", "Tech"),
                ("TSLA", "Automotriz"),
                ("MSFT", "Tech")
            ]
            
            # O puedes usar los Penny Stocks si quieres:
            activos = []
            if FMP_API_KEY:
                try:
                    url_fmp = f"https://financialmodelingprep.com/api/v3/stock_screener?priceLowerThan=5&volumeMoreThan=1000000&limit=5&apikey={FMP_API_KEY}"
                    data_fmp = requests.get(url_fmp, timeout=10).json()
                    activos = [(item['symbol'], item.get('sector', 'Penny Stock')) for item in data_fmp]
                except Exception as e:
                    print(f"Error FMP: {e}")
                    activos = []
            
            # Combinar listas (prioriza globales para pruebas)
            todos_activos = globales + activos[:5]  # Máximo 10 activos total
            
            print(f"Analizando {len(todos_activos)} activos...")
            
            for t, s in todos_activos:
                await procesar_activo(t, s)
                await asyncio.sleep(3)  # Pausa entre activos
            
            print(f"✅ Ciclo completado a las {datetime.now()}. Esperando 30 minutos...")
            await asyncio.sleep(60)  # 30 minutos entre ciclos
            
        except Exception as e:
            print(f"Error en main_loop: {e}")
            await asyncio.sleep(300)

# --- PRUEBA DE COMUNICACIÓN DIRECTA ---
async def test_telegram():
    try:
        print("📡 Intentando enviar mensaje de prueba a Telegram...")
        await bot.send_message(
            chat_id=CHAT_ID, 
            text=f"✅ CONEXIÓN EXITOSA: INVESTFRED AI v14.0\n"
                 f"Hora: {datetime.now()}\n"
                 f"Bot iniciado correctamente en Render."
        )
        print("✅ Mensaje de prueba enviado con éxito.")
    except Exception as e:
        print(f"❌ ERROR DE TELEGRAM: {e}")

# --- INICIO DEL PROGRAMA ---
if __name__ == "__main__":
    print("Iniciando INVESTFRED AI...")
    
    # Verificar variables de entorno
    if not TOKEN or not CHAT_ID:
        print("❌ ERROR: Faltan variables de entorno (telegram_token o chat_ID)")
    else:
        print("✅ Variables de entorno cargadas correctamente")
    
    # Iniciar servidor web en segundo plano
    Thread(target=run_web, daemon=True).start()
    print("🌐 Servidor web iniciado en puerto 8080")
    
    # Ejecutar bot
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Primero enviar mensaje de prueba
        loop.run_until_complete(test_telegram())
        
        # Esperar 5 segundos antes de empezar análisis
        time.sleep(5)
        
        # Iniciar el ciclo principal
        print("🔄 Iniciando ciclo de análisis principal...")
        loop.run_until_complete(main_loop())
        
    except KeyboardInterrupt:
        print("\n⏹️ Bot detenido manualmente")
    except Exception as e:
        print(f"❌ Error crítico: {e}")
