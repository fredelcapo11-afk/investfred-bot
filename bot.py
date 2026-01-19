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
from supabase import create_client, Client # Necesitas pip install supabase

# --- CONFIGURACIÓN ---
TOKEN = os.getenv('telegram_token')
CHAT_ID = os.getenv('chat_ID')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
RENDER_APP_URL = os.getenv('RENDER_EXTERNAL_URL')

bot = Bot(token=TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- TUS ACTIVOS ---
CRYPTO_ACTIVOS = [("BTC-USD", "Bitcoin"), ("ETH-USD", "Ethereum"), ("SOL-USD", "Solana"), ("LINK-USD", "Chainlink"), ("AAVE-USD", "Aave")]
COMMODITIES_ACTIVOS = [("GC=F", "Oro"), ("CL=F", "Petróleo")]
COLOMBIAN_ACTIVOS = [("EC", "Ecopetrol"), ("ISA", "ISA")]

# =================================================================
# 🗄️ LÓGICA DE BASE DE DATOS (SUPABASE)
# =================================================================

def guardar_señal_db(ticker, precio):
    supabase.table("señales").insert({
        "ticker": ticker, 
        "precio_entrada": precio, 
        "evaluada": False
    }).execute()

async def generar_reporte_semanal():
    res = supabase.table("señales").select("*").not_.is_("resultado", "null").execute()
    señales = res.data
    if not señales: return "Sin datos históricos en la base de datos."

    ganadas = sum(1 for s in señales if s["resultado"] == "GANADA")
    win_rate = (ganadas / len(señales)) * 100
    return (f"📊 **REPORTE SEMANAL (DESDE SUPABASE)**\n"
            f"📈 Win Rate: {win_rate:.1f}%\n"
            f"✅ Ganadas: {ganadas} | ❌ Perdidas: {len(señales)-ganadas}")

async def verificar_resultados_db():
    res = supabase.table("señales").select("*").eq("evaluada", False).execute()
    for s in res.data:
        df = yf.download(s["ticker"], period="1d", interval="15m", progress=False)
        if not df.empty:
            precio_actual = df['Close'].iloc[-1]
            resultado = "GANADA" if precio_actual > s["precio_entrada"] else "PERDIDA"
            supabase.table("señales").update({"resultado": resultado, "evaluada": True}).eq("id", s["id"]).execute()

# =================================================================
# 🚀 ESCANEO Y ML
# =================================================================

async def procesar_activo(ticker, nombre):
    try:
        df = yf.download(ticker, period='5d', interval='15m', prepost=True, progress=False)
        if len(df) < 30: return

        # ML simplificado
        df['RSI'] = ta.rsi(df['Close'], length=14)
        df['Target'] = (df['Close'].shift(-4) > df['Close']).astype(int)
        df_ml = df.dropna()
        
        X = df_ml[['Close', 'RSI']].tail(20)
        y = df_ml['Target'].tail(20)
        prob = RandomForestClassifier(n_estimators=50).fit(X[:-1], y[:-1]).predict_proba(X.tail(1))[:,1][0]
        
        vol_rel = df['Volume'].iloc[-1] / df['Volume'].rolling(20).mean().iloc[-1]

        if prob > 0.63 or vol_rel > 2.2:
            precio = float(df['Close'].iloc[-1])
            guardar_señal_db(ticker, precio)
            await bot.send_message(chat_id=CHAT_ID, text=f"🚀 **SEÑAL:** {ticker}\nProb IA: {prob:.1%}\nVol: {vol_rel:.1f}x", parse_mode='Markdown')
    except: pass

async def main_loop():
    while True:
        for ticker, nombre in CRYPTO_ACTIVOS + COMMODITIES_ACTIVOS + COLOMBIAN_ACTIVOS:
            await procesar_activo(ticker, nombre)
            await asyncio.sleep(2)
        
        await verificar_resultados_db()
        
        # Reporte Domingos 8 PM
        tz_col = pytz.timezone('America/Bogota')
        ahora = datetime.now(tz_col)
        if ahora.weekday() == 6 and ahora.hour == 20 and ahora.minute < 30:
            msg = await generar_reporte_semanal()
            await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')
            await asyncio.sleep(2000)

        if RENDER_APP_URL: requests.get(RENDER_APP_URL)
        await asyncio.sleep(900)

app = Flask('')
@app.route('/')
def home(): return "INVESTFRED AI + SUPABASE"

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))).start()
    asyncio.run(main_loop())
