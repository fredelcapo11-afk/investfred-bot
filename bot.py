import yfinance as yf
import pandas as pd
import telebot
import matplotlib.pyplot as plt
import io
import os
import time

# --- CONFIGURACIÓN DE CRIPTO Y TELEGRAM ---
# Se usan exactamente los nombres de tus Secrets en Fly.io
TOKEN = os.getenv('telegram_token') # Coincide con tu captura de Secrets
CHAT_ID = os.getenv('chat_ID')      # Coincide con tu captura de Secrets
bot = telebot.TeleBot(TOKEN)

def calcular_rsi_manual(series, window=14):
    """Calcula el RSI sin depender de librerías externas para evitar errores en Fly.io"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def obtener_analisis(symbol="BTC-USD"):
    try:
        # Descargar datos
        df = yf.download(symbol, period="1d", interval="15m")
        if df.empty:
            return None
        
        # Asegurar que los datos sean planos para los gráficos
        df_close = df['Close'].squeeze().astype(float)
        
        # CÁLCULO DE INDICADORES
        df['RSI'] = calcular_rsi_manual(df_close)
        
        # CREACIÓN DEL GRÁFICO
        plt.figure(figsize=(12, 8))
        
        # Subtrama 1: Precio
        plt.subplot(2, 1, 1)
        plt.plot(df_close.index, df_close, label='Precio Close', color='blue')
        plt.title(f"Análisis Técnico Real-time: {symbol}")
        plt.legend()
        plt.grid(True)

        # Subtrama 2: RSI
        plt.subplot(2, 1, 2)
        plt.plot(df.index, df['RSI'], label='RSI (14)', color='purple')
        plt.axhline(70, linestyle='--', color='red', alpha=0.5)
        plt.axhline(30, linestyle='--', color='green', alpha=0.5)
        plt.ylim(0, 100)
        plt.legend()
        plt.grid(True)

        # Guardar gráfico en memoria
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        
        # Determinar señal
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

if __name__ == "__main__":
    print("🚀 INVESTFRED v16.9: Parche RSI Manual y Gráficos Activado...")
    
    # BUCLE INFINITO: Esto evita que el bot se apague y crashee en Fly.io
    while True:
        try:
            enviar_señal()
            print("✅ Señal enviada con éxito. Esperando 15 minutos...")
            time.sleep(900) # Espera 15 minutos para la siguiente señal
        except Exception as e:
            print(f"Error en el ciclo: {e}")
            time.sleep(60) # Si falla, reintenta en 1 minuto
