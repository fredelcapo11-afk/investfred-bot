import yfinance as yf
import pandas as pd
import telebot
import matplotlib.pyplot as plt
import io
import os
import time
from flask import Flask
from threading import Thread

# --- 1. CONFIGURACIÓN DE CRIPTO Y TELEGRAM ---
TOKEN = os.getenv('telegram_token')
CHAT_ID = os.getenv('chat_ID')
bot = telebot.TeleBot(TOKEN)

# --- 2. SERVIDOR WEB PARA RENDER (FLASK) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# --- 3. FUNCIONES DE ANÁLISIS ---
def calcular_rsi_manual(series, window=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def obtener_analisis(symbol="BTC-USD"):
    try:
        df = yf.download(symbol, period="1d", interval="15m")
        if df.empty:
            return None
        
        df_close = df['Close'].squeeze().astype(float)
        df['RSI'] = calcular_rsi_manual(df_close)
        
        plt.figure(figsize=(12, 8))
        plt.subplot(2, 1, 1)
        plt.plot(df_close.index, df_close, label='Precio Close', color='blue')
        plt.title(f"Análisis Técnico Real-time: {symbol}")
        plt.legend()
        plt.grid(True)

        plt.subplot(2, 1, 2)
        plt.plot(df.index, df['RSI'], label='RSI (14)', color='purple')
        plt.axhline(70, linestyle='--', color='red', alpha=0.5)
        plt.axhline(30, linestyle='--', color='green', alpha=0.5)
        plt.ylim(0, 100)
        plt.legend()
        plt.grid(True)

        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        
        ultimo_rsi = df['RSI'].iloc[-1]
        señal = "NEUTRAL ⚪"
        if ultimo_rsi < 35: señal = "COMPRA (RSI Bajo) 🟢"
        elif ultimo_rsi > 65: señal = "VENTA (RSI Alto) 🔴"
        
        mensaje = f"🚀 **SEÑAL {symbol}**\n\n💰 Precio: {df_close.iloc[-1]:.2f}\n📊 RSI: {ultimo_rsi:.2f}\n⚡ Acción: {señal}"
        return buf, mensaje

    except Exception as e:
        print(f"Error en análisis: {e}")
        return None

def enviar_señal():
    resultado = obtener_analisis()
    if resultado:
        img, texto = resultado
        bot.send_photo(CHAT_ID, img, caption=texto, parse_mode="Markdown")

# --- 4. BLOQUE PRINCIPAL ---
if __name__ == "__main__":
    print("🚀 INVESTFRED v16.9: Servidor Web y Bot Iniciando...")
    
    # Iniciar servidor web en segundo plano
    Thread(target=run_flask).start()
    
    # Bucle principal del bot
    while True:
        try:
            enviar_señal()
            print("✅ Señal enviada con éxito. Esperando 15 minutos...")
            time.sleep(900) # 15 minutos evita bloqueos de Yahoo Finance
        except Exception as e:
            print(f"Error en el ciclo: {e}")
            time.sleep(60) # Reintento en 1 minuto si hay error


