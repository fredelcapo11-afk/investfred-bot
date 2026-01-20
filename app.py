# app.py - INVESTFRED AI Bot para Render
import yfinance as yf
import pandas_ta as ta
import asyncio
import pandas as pd
import os
import requests
import time
import json
from telegram import Bot
from datetime import datetime, timedelta
from sklearn.ensemble import RandomForestClassifier
from flask import Flask
from threading import Thread
from textblob import TextBlob
import pytz
import holidays
import warnings

warnings.filterwarnings("ignore")

# --- CONFIGURACIÓN ---
TOKEN = os.getenv('telegram_token')
CHAT_ID = os.getenv('chat_ID')
FMP_API_KEY = os.getenv('fmp_api_key')
bot = Bot(token=TOKEN)

# =================================================================
# ⚙️ CONFIGURACIÓN DE UMBRALES - ¡AQUÍ AJUSTAS EL 70%!
# =================================================================

# UMBRALES DE PROBABILIDAD POR TIPO DE ACTIVO (70% configurado)
UMBRALES = {
    'CRYPTO': 0.70,        # 70% para criptomonedas
    'COMMODITY': 0.70,     # 70% para commodities
    'COLOMBIA': 0.70,      # 70% para acciones colombianas
    'PENNY_STOCK': 0.70,   # 70% para penny stocks
    'ETF': 0.70,           # 70% para ETFs
    'DEFAULT': 0.70        # 70% para cualquier otro
}

# Umbrales de RSI
RSI_UMBRALES = {
    'CRYPTO': (30, 70),
    'COMMODITY': (35, 65),
    'COLOMBIA': (35, 65),
    'PENNY_STOCK': (40, 60),
    'ETF': (35, 65),
    'DEFAULT': (35, 65)
}

# Umbrales de volumen mínimo
VOLUMEN_UMBRALES = {
    'CRYPTO': 1.2,
    'COMMODITY': 1.3,
    'COLOMBIA': 1.4,
    'PENNY_STOCK': 1.5,
    'ETF': 1.3,
    'DEFAULT': 1.3
}

# =================================================================

# --- CONFIGURACIÓN DE HORARIOS ---
class HorarioBursatil:
    def __init__(self):
        self.ny_tz = pytz.timezone('America/New_York')
        self.col_tz = pytz.timezone('America/Bogota')
        self.us_holidays = holidays.US(years=datetime.now().year)
    
    def es_horario_bursatil_ny(self):
        ahora_ny = datetime.now(self.ny_tz)
        
        if ahora_ny.weekday() >= 5:
            return False
        
        if ahora_ny.date() in self.us_holidays:
            return False
        
        hora_actual = ahora_ny.strftime('%H:%M')
        return '09:30' <= hora_actual <= '16:00'
    
    def es_horario_bursatil_col(self):
        ahora_col = datetime.now(self.col_tz)
        
        if ahora_col.weekday() >= 5:
            return False
        
        hora_actual = ahora_col.strftime('%H:%M')
        return '09:00' <= hora_actual <= '16:00'
    
    def obtener_info_mercados(self):
        ahora_ny = datetime.now(self.ny_tz)
        ahora_col = datetime.now(self.col_tz)
        
        return {
            'ny_abierto': self.es_horario_bursatil_ny(),
            'col_abierto': self.es_horario_bursatil_col(),
            'hora_ny': ahora_ny.strftime('%H:%M'),
            'hora_col': ahora_col.strftime('%H:%M'),
            'dia_semana': ahora_ny.strftime('%A'),
            'crypto_abierto': True
        }

horario = HorarioBursatil()

# --- LISTAS OPTIMIZADAS ---

# 1. CRIPTOMONEDAS RWA
CRYPTO_ACTIVOS = [
    ("BTC-USD", "Bitcoin", "🪙 Crypto"),
    ("ETH-USD", "Ethereum", "🪙 Crypto"),
    ("BNB-USD", "Binance Coin", "🪙 Crypto"),
    ("SOL-USD", "Solana", "🪙 Crypto"),
    ("ADA-USD", "Cardano", "🪙 Crypto")
]

# 2. COMMODITIES
COMMODITIES_ACTIVOS = [
    ("GC=F", "Oro", "🥇 Commodity"),
    ("SI=F", "Plata", "🥈 Commodity"),
    ("CL=F", "Petróleo", "🛢️ Commodity")
]

# 3. ACCIONES COLOMBIANAS
COLOMBIAN_ACTIVOS = [
    ("EC", "Ecopetrol", "🇨🇴 Colombia"),
    ("ISA", "ISA", "🇨🇴 Colombia")
]

# 4. ETFs
ETF_ACTIVOS = [
    ("XLF", "Financial ETF", "🏦 ETF")
]

def obtener_penny_stocks_dinamicos(limit=5):
    """Obtiene penny stocks en tiempo real"""
    if not FMP_API_KEY:
        return []
    
    try:
        url = f"https://financialmodelingprep.com/api/v3/stock-screener?"
        url += f"marketCapLowerThan=500000000&"
        url += f"priceLowerThan=3&"
        url += f"volumeMoreThan=5000000&"
        url += f"limit={limit}&"
        url += f"apikey={FMP_API_KEY}"
        
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data:
            return [(item['symbol'], 
                    item.get('companyName', 'Penny')[:20], 
                    f"🎯 Penny") 
                   for item in data[:3]]
        return []
            
    except Exception as e:
        print(f"Error penny stocks: {e}")
        return []

# --- FUNCIONES DE ANÁLISIS ---
def analizar_activo_avanzado(df, ticker):
    """Análisis técnico completo"""
    try:
        analysis = {}
        
        # Precios
        analysis['precio'] = float(df['Close'].iloc[-1])
        analysis['volumen'] = int(df['Volume'].iloc[-1])
        
        # Indicadores
        analysis['rsi'] = ta.rsi(df['Close'], length=14).iloc[-1]
        
        macd = ta.macd(df['Close'])
        analysis['macd'] = macd['MACD_12_26_9'].iloc[-1]
        analysis['macd_signal'] = macd['MACDS_12_26_9'].iloc[-1]
        
        analysis['sma_20'] = ta.sma(df['Close'], length=20).iloc[-1]
        analysis['sma_50'] = ta.sma(df['Close'], length=50).iloc[-1]
        
        # Volumen relativo
        vol_promedio = df['Volume'].rolling(20).mean().iloc[-1]
        analysis['vol_relativo'] = analysis['volumen'] / vol_promedio if vol_promedio > 0 else 1
        
        # Señales
        analysis['señal_rsi'] = "Sobreventa" if analysis['rsi'] < 30 else "Sobrecompra" if analysis['rsi'] > 70 else "Neutral"
        analysis['señal_macd'] = "Alcista" if analysis['macd'] > analysis['macd_signal'] else "Bajista"
        analysis['señal_tendencia'] = "Alcista" if analysis['precio'] > analysis['sma_20'] > analysis['sma_50'] else "Bajista"
        
        return analysis
    except Exception as e:
        print(f"Error análisis {ticker}: {e}")
        return None

def obtener_sentimiento_noticias(ticker):
    """Obtiene sentimiento de noticias"""
    if not FMP_API_KEY:
        return 0
    
    try:
        url = f"https://financialmodelingprep.com/api/v3/stock_news?tickers={ticker}&limit=5&apikey={FMP_API_KEY}"
        response = requests.get(url, timeout=10)
        news = response.json()
        
        if not news: 
            return 0
        
        sentiment_score = 0
        for item in news[:3]:
            analysis = TextBlob(item['title'])
            sentiment_score += analysis.sentiment.polarity
        
        avg_sentiment = sentiment_score / len(news[:3]) if news[:3] else 0
        return avg_sentiment * 0.08
        
    except Exception:
        return 0

def predecir_tendencia_ml_estricta(df, ticker, tipo_activo):
    """Predicción ML"""
    try:
        data = df.copy()
        
        # Preparar características
        data['Target'] = (data['Close'].shift(-2) > data['Close'].shift(-1)).astype(int)
        
        data['RSI'] = ta.rsi(data['Close'], length=14)
        
        macd = ta.macd(data['Close'])
        data['MACD'] = macd['MACD_12_26_9']
        data['MACD_Signal'] = macd['MACDS_12_26_9']
        
        data['SMA_20'] = ta.sma(data['Close'], length=20)
        data['SMA_50'] = ta.sma(data['Close'], length=50)
        
        data['Vol_Rel'] = data['Volume'] / data['Volume'].rolling(20).mean()
        
        data = data.dropna()
        
        if len(data) < 50:
            return 0.5
        
        # Características
        features = ['RSI', 'MACD', 'SMA_20', 'SMA_50', 'Vol_Rel']
        
        X = data[features]
        y = data['Target']
        
        model = RandomForestClassifier(
            n_estimators=100, 
            random_state=42,
            max_depth=8
        )
        
        train_size = int(len(X) * 0.85)
        X_train, y_train = X[:train_size], y[:train_size]
        
        model.fit(X_train, y_train)
        
        prob_base = model.predict_proba(X.tail(3))[:, 1].mean()
        
        # Ajustar por tipo
        ajuste_tipo = {
            'CRYPTO': 1.05,
            'COMMODITY': 1.0,
            'COLOMBIA': 0.95,
            'PENNY_STOCK': 0.9,
            'ETF': 1.0,
            'DEFAULT': 1.0
        }
        
        sentimiento = obtener_sentimiento_noticias(ticker)
        
        prob_ajustada = prob_base * ajuste_tipo.get(tipo_activo, 1.0)
        prob_final = prob_ajustada + sentimiento
        
        # Limitar entre 0 y 1
        return max(0, min(1, prob_final))
        
    except Exception as e:
        print(f"Error ML {ticker}: {e}")
        return 0.5

# =================================================================
# 🎯 FUNCIÓN PRINCIPAL CON FILTRO 70%
# =================================================================
async def procesar_activo_con_filtro_70(ticker, nombre, categoria, tipo_activo):
    """Procesa un activo con filtro estricto del 70%"""
    print(f"🔍 Analizando: {ticker}")
    
    try:
        # Configurar parámetros según tipo
        config = {
            'CRYPTO': {'interval': '30m', 'period': '10d'},
            'COMMODITY': {'interval': '1h', 'period': '1mo'},
            'COLOMBIA': {'interval': '1h', 'period': '1mo'},
            'PENNY_STOCK': {'interval': '30m', 'period': '1mo'},
            'ETF': {'interval': '1h', 'period': '1mo'},
            'DEFAULT': {'interval': '1h', 'period': '1mo'}
        }
        
        cfg = config.get(tipo_activo, config['DEFAULT'])
        
        # Descargar datos
        df = yf.download(ticker, period=cfg['period'], interval=cfg['interval'], 
                        progress=False, timeout=15)
        
        if df is None or df.empty or len(df) < 30:
            return
        
        if isinstance(df.columns, pd.MultiIndex): 
            df.columns = df.columns.get_level_values(0)
        
        # Análisis
        analisis = analizar_activo_avanzado(df, ticker)
        if not analisis:
            return
        
        # Predicción ML
        prob = predecir_tendencia_ml_estricta(df, ticker, tipo_activo)
        
        # Obtener umbrales
        umbral_prob = UMBRALES[tipo_activo]
        rsi_min, rsi_max = RSI_UMBRALES[tipo_activo]
        vol_minimo = VOLUMEN_UMBRALES[tipo_activo]
        
        # FILTRO PRINCIPAL: 70% O MÁS
        if prob >= umbral_prob:
            # Verificar condiciones
            rsi_ok = rsi_min <= analisis['rsi'] <= rsi_max
            vol_ok = analisis['vol_relativo'] >= vol_minimo
            tendencia_ok = analisis['señal_tendencia'] == "Alcista"
            macd_ok = analisis['señal_macd'] == "Alcista"
            
            condiciones_cumplidas = sum([rsi_ok, vol_ok, tendencia_ok, macd_ok])
            
            # Requerir 3 de 4 condiciones
            if condiciones_cumplidas >= 3:
                # GENERAR SEÑAL
                precio = analisis['precio']
                
                emojis = {
                    'CRYPTO': '🪙',
                    'COMMODITY': '📊',
                    'COLOMBIA': '🇨🇴',
                    'PENNY_STOCK': '🎯',
                    'ETF': '📈'
                }
                
                emoji = emojis.get(tipo_activo, '📊')
                
                msg = (f"{emoji} **🚨 SEÑAL ALTA PROBABILIDAD 🚨**\n"
                      f"**Activo:** `{ticker}`\n"
                      f"**Nombre:** {nombre}\n"
                      f"**Precio:** ${precio:.2f}\n\n"
                      f"**📊 PROBABILIDAD IA:** {prob:.1%} (Umbral: {umbral_prob*100}%)\n\n"
                      f"**🔍 CONDICIONES:**\n"
                      f"{'✅' if rsi_ok else '❌'} RSI: {analisis['rsi']:.1f}\n"
                      f"{'✅' if vol_ok else '❌'} Volumen: {analisis['vol_relativo']:.1f}x\n"
                      f"{'✅' if tendencia_ok else '❌'} Tendencia: {analisis['señal_tendencia']}\n"
                      f"{'✅' if macd_ok else '❌'} MACD: {analisis['señal_macd']}\n\n"
                      f"**⏰ Hora:** {datetime.now().strftime('%H:%M:%S')}")
                
                await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')
                print(f"✅ SEÑAL ENVIADA: {ticker} con {prob:.1%}")
                
    except Exception as e:
        print(f"Error {ticker}: {e}")

# --- BUCLE PRINCIPAL CON 70% ---
async def main_loop_con_70():
    """Bucle principal con filtro del 70%"""
    print("🤖 INVESTFRED AI - FILTRO 70% ACTIVADO")
    
    ciclo = 0
    
    while True:
        try:
            ciclo += 1
            ahora = datetime.now()
            
            mercados = horario.obtener_info_mercados()
            es_horario_ny = mercados['ny_abierto']
            es_horario_col = mercados['col_abierto']
            
            print(f"\n🔄 CICLO #{ciclo} - {ahora.strftime('%H:%M')}")
            
            # LISTA DE ACTIVOS
            activos_a_analizar = []
            
            # 1. CRIPTOMONEDAS (SIEMPRE)
            for ticker, nombre, categoria in CRYPTO_ACTIVOS:
                activos_a_analizar.append((ticker, nombre, categoria, 'CRYPTO'))
            
            # 2. COMMODITIES (Horario NY)
            if es_horario_ny:
                for ticker, nombre, categoria in COMMODITIES_ACTIVOS:
                    activos_a_analizar.append((ticker, nombre, categoria, 'COMMODITY'))
            
            # 3. ACCIONES COLOMBIANAS
            if es_horario_col or es_horario_ny:
                for ticker, nombre, categoria in COLOMBIAN_ACTIVOS:
                    activos_a_analizar.append((ticker, nombre, categoria, 'COLOMBIA'))
            
            # 4. PENNY STOCKS (Solo NY)
            if es_horario_ny and FMP_API_KEY and ciclo % 3 == 0:
                penny_stocks = obtener_penny_stocks_dinamicos(limit=3)
                for ticker, nombre, categoria in penny_stocks:
                    activos_a_analizar.append((ticker, nombre, categoria, 'PENNY_STOCK'))
            
            # 5. ETF (Solo NY)
            if es_horario_ny:
                for ticker, nombre, categoria in ETF_ACTIVOS:
                    activos_a_analizar.append((ticker, nombre, categoria, 'ETF'))
            
            # Eliminar duplicados
            seen = set()
            activos_unicos = []
            for activo in activos_a_analizar:
                ticker = activo[0]
                if ticker not in seen:
                    seen.add(ticker)
                    activos_unicos.append(activo)
            
            print(f"📊 ACTIVOS: {len(activos_unicos)}")
            
            # ANALIZAR
            for ticker, nombre, categoria, tipo in activos_unicos:
                await procesar_activo_con_filtro_70(ticker, nombre, categoria, tipo)
                await asyncio.sleep(1.5)
            
            # TIEMPO DE ESPERA
            if es_horario_ny:
                wait_time = 1800  # 30 minutos
            elif es_horario_col and not es_horario_ny:
                wait_time = 2400  # 40 minutos
            else:
                wait_time = 3600  # 1 hora
            
            print(f"⏰ Esperando {wait_time//60}min...")
            await asyncio.sleep(wait_time)
            
        except Exception as e:
            print(f"Error ciclo: {e}")
            await asyncio.sleep(300)

# --- SERVIDOR WEB ---
app = Flask('')
@app.route('/')
def home():
    mercados = horario.obtener_info_mercados()
    return f"""
    <html>
    <head><title>INVESTFRED AI - 70%</title>
    <style>
        body {{ font-family: Arial; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        .status {{ display: flex; justify-content: space-between; background: #e8f6f3; padding: 15px; border-radius: 8px; margin: 20px 0; }}
        .status-item {{ text-align: center; }}
    </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 INVESTFRED AI - UMBRAL 70%</h1>
            
            <div style="background:#e8f4fc; padding:15px; border-radius:8px; margin:20px 0; border-left:5px solid #3498db;">
                <h3 style="color:#2980b9; margin-top:0;">🎯 CONFIGURACIÓN DE UMBRALES</h3>
                <p><strong>Umbral mínimo de probabilidad: 70%</strong></p>
                <p>Solo señales con probabilidad ≥ 70%</p>
            </div>
            
            <div class="status">
                <div class="status-item">
                    <strong>NYSE/NASDAQ</strong><br>
                    <span style="color: {'#27ae60' if mercados['ny_abierto'] else '#e74c3c'}; font-weight:bold;">
                        {mercados['hora_ny']} ({'✅ ABIERTO' if mercados['ny_abierto'] else '🔴 CERRADO'})
                    </span>
                </div>
                <div class="status-item">
                    <strong>BVC Colombia</strong><br>
                    <span style="color: {'#27ae60' if mercados['col_abierto'] else '#e74c3c'}; font-weight:bold;">
                        {mercados['hora_col']} ({'✅ ABIERTO' if mercados['col_abierto'] else '🔴 CERRADO'})
                    </span>
                </div>
                <div class="status-item">
                    <strong>Día</strong><br>
                    {mercados['dia_semana']}
                </div>
            </div>
            
            <div style="background:#f8f9fa; padding:20px; border-radius:8px; margin:20px 0;">
                <h3>📊 ACTIVOS MONITOREADOS</h3>
                <ul style="list-style:none; padding:0;">
                    <li>🪙 <strong>Criptomonedas:</strong> Umbral 70%</li>
                    <li>🥇 <strong>Commodities:</strong> Umbral 70%</li>
                    <li>🇨🇴 <strong>Acciones Colombianas:</strong> Umbral 70%</li>
                    <li>🎯 <strong>Penny Stocks:</strong> Umbral 70%</li>
                    <li>📈 <strong>ETF XLF:</strong> Umbral 70%</li>
                </ul>
                <p><em>Bot activo y monitoreando mercados</em></p>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    return json.dumps({"status": "ok", "time": datetime.now().isoformat()})

@app.route('/config')
def mostrar_config():
    return json.dumps({
        "umbrales": UMBRALES,
        "activos": {
            "criptos": len(CRYPTO_ACTIVOS),
            "commodities": len(COMMODITIES_ACTIVOS),
            "colombia": len(COLOMBIAN_ACTIVOS)
        }
    }, indent=2)

# --- INICIO CON 70% ---
async def inicio_con_70():
    """Secuencia de inicio"""
    try:
        mercados = horario.obtener_info_mercados()
        
        msg = (f"🚀 **INVESTFRED AI INICIADO - UMBRAL 70%**\n\n"
               f"🎯 **CONFIGURACIÓN:**\n"
               f"• Mínimo: 70% de probabilidad\n"
               f"• Crypto: 70%\n"
               f"• Commodities: 70%\n"
               f"• Colombia: 70%\n"
               f"• Penny: 70%\n"
               f"• ETF: 70%\n\n"
               f"📅 **HORARIOS:**\n"
               f"• NY: {mercados['hora_ny']} ({'✅' if mercados['ny_abierto'] else '⏸️'})\n"
               f"• CO: {mercados['hora_col']} ({'✅' if mercados['col_abierto'] else '⏸️'})\n"
               f"• Día: {mercados['dia_semana']}\n\n"
               f"🔔 **SOLO señales de ALTA PROBABILIDAD.**")
        
        await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')
        print("✅ Bot iniciado con umbral 70%")
        
    except Exception as e:
        print(f"❌ Error inicio: {e}")

# =================================================================
# 🚀 PUNTO DE ENTRADA OPTIMIZADO PARA RENDER
# =================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("🤖 INVESTFRED AI - CONFIGURACIÓN 70%")
    print("=" * 60)
    
    # Verificar variables
    if not TOKEN or not CHAT_ID:
        print("❌ ERROR: Faltan telegram_token o chat_ID")
        print("   Configura las variables en Render Dashboard > Environment")
        exit(1)
    
    # Función para ejecutar el bot en un thread separado
    def ejecutar_bot():
        try:
            # Crear nuevo event loop para el thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Iniciar bot
            loop.run_until_complete(inicio_con_70())
            time.sleep(2)
            
            # Ejecutar bucle principal
            print("\n🔄 Iniciando ciclo principal...")
            loop.run_until_complete(main_loop_con_70())
            
        except Exception as e:
            print(f"💥 Error crítico en bot: {e}")
            # Intentar reiniciar después de 5 minutos
            time.sleep(300)
            ejecutar_bot()
    
    # Iniciar el bot en un thread DAEMON (no bloquea Flask)
    bot_thread = Thread(target=ejecutar_bot, daemon=True)
    bot_thread.start()
    print("✅ Bot iniciado en thread separado")
    
    # Iniciar servidor Flask (OBLIGATORIO para Render)
    print("🌐 Iniciando servidor web Flask...")
    port = int(os.environ.get('PORT', 10000))
    
    # Desactivar reloader para evitar problemas en Render
    app.run(
        host='0.0.0.0',
        port=port,
        debug=False,
        use_reloader=False
    )
