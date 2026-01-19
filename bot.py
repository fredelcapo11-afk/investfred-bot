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
import pytz
from supabase import create_client, Client
import warnings

warnings.filterwarnings("ignore")

# --- CONFIGURACIÓN ---
TOKEN = os.getenv('telegram_token')
CHAT_ID = os.getenv('chat_ID')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
RENDER_APP_URL = os.getenv('RENDER_EXTERNAL_URL')

bot = Bot(token=TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- ACTIVOS ---
CRYPTO = [("BTC-USD", "Bitcoin"), ("ETH-USD", "Ethereum"), ("SOL-USD", "Solana"), ("LINK-USD", "Chainlink")]
COMMODITIES = [("GC=F", "Oro"), ("CL=F", "Petróleo")]
STOCKS = [("EC", "Ecopetrol")]

# =================================================================
# 🗄️ BASE DE DATOS Y REPORTES
# =================================================================

def guardar_señal_db(ticker, precio):
    try:
        supabase.table("señales").insert({
            "ticker": ticker, 
            "precio_entrada": precio, 
            "evaluada": False
        }).execute()
    except Exception as e:
        print(f"Error DB: {e}")

async def verificar_resultados_db():
    try:
        res = supabase.table("señales").select("*").eq("evaluada", False).execute()
        for s in res.data:
            df = yf.download(s["ticker"], period="1d", interval="15m", progress=False)
            if not df.empty:
                precio_actual = float(df['Close'].iloc[-1])
                # Criterio simple: si subió es GANADA
                resultado = "GANADA" if precio_actual > s["precio_entrada"] else "PERDIDA"
                supabase.table("señales").update({
                    "resultado": resultado, 
                    "evaluada": True
                }).eq("id", s["id"]).execute()
    except Exception as e:
        print(f"Error verificación: {e}")

async def generar_reporte_semanal():
    res = supabase.table("señales").select("*").not_.is_("resultado", "null").execute()
    señales = res.data
    if not señales: return "📊 Aún no hay historial suficiente para el reporte."

    ganadas = sum(1 for s in señales if s["resultado"] == "GANADA")
    win_rate = (ganadas / len(señales)) * 100
    return (f"📊 **REPORTE DE PRECISIÓN SEMANAL**\n"
            f"📈 Win Rate: {win_rate:.1f}%\n"
            f"✅ Ganadas: {ganadas}\n"
            f"❌ Perdidas: {len(señales)-ganadas}\n"
            f"Total analizadas: {len(señales)}")

# =================================================================
# 🧠 INTELIGENCIA ARTIFICIAL (ML)
# =================================================================

async def procesar_activo(ticker, nombre):
    try:
        df = yf.download(ticker, period='5d', interval='15m', prepost=True, progress=False)
        if len(df) < 30: return

        df['RSI'] = ta.rsi(df['Close'], length=14)
        df['Target'] = (df['Close'].shift(-4) > df['Close']).astype(int)
        df_ml = df.dropna()
        
        X = df_ml[['Close', 'RSI']].tail(20)
        y = df_ml['Target'].tail(20)
        
        model = RandomForestClassifier(n_estimators=50)
        model.fit(X[:-1], y[:-1])
        prob = model.predict_proba(X.tail(1))[:, 1][0]
        
        vol_rel = df['Volume'].iloc[-1] / df['Volume'].rolling(20).mean().iloc[-1]

        # DISPARADOR: IA > 63% o Volumen > 2.2x
        if prob > 0.63 or vol_rel > 2.2:
            precio = float(df['Close'].iloc[-1])
            guardar_señal_db(ticker, precio)
            
            msg = (f"🚀 **SEÑAL DETECTADA**\n"
                   f"Activo: `{ticker}`\n"
                   f"IA Prob: {prob:.1%}\n"
                   f"Volumen: {vol_rel:.1f}x\n"
                   f"Precio: ${precio:.2f}")
            await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')
    except:
        pass

# =================================================================
# 🚀 BUCLE PRINCIPAL
# =================================================================

async def main_loop():
    while True:
        print("Iniciando escaneo...")
        for ticker, nombre in CRYPTO + COMMODITIES + STOCKS:
            await procesar_activo(ticker, nombre)
            await asyncio.sleep(2)

        # Verificar si señales pasadas ya cerraron
        await verificar_resultados_db()

        # --- FUNCIÓN HEARTBEAT (AVISO DE VIDA) ---
        tz_col = pytz.timezone('America/Bogota')
        ahora_col = datetime.now(tz_col).strftime("%H:%M")
        await bot.send_message(
            chat_id=CHAT_ID, 
            text=f"✅ **Ciclo completado** ({ahora_col})\nStatus: Buscando señales...",
            parse_mode='Markdown'
        )

        # Reporte semanal (Domingos 8 PM Col)
        ahora = datetime.now(tz_col)
        if ahora.weekday() == 6 and ahora.hour == 20 and ahora.minute < 30:
            reporte = await generar_reporte_semanal()
            await bot.send_message(chat_id=CHAT_ID, text=reporte, parse_mode='Markdown')
            await asyncio.sleep(2000)

        # Auto-Ping para Render
        if RENDER_APP_URL:
            try: requests.get(RENDER_APP_URL)
            except: pass

        await asyncio.sleep(900) # Esperar 15 min

# --- SERVIDOR WEB ---
app = Flask('')
@app.route('/')
def home(): return "INVESTFRED AI - LIVE"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    asyncio.run(main_loop())
