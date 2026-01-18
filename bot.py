import yfinance as yf
import pandas_ta as ta
import asyncio
import pandas as pd
import os
import requests
import matplotlib.pyplot as plt
import io
import time
import json
from telegram import Bot
from datetime import datetime, timedelta
from sklearn.ensemble import RandomForestClassifier
from flask import Flask
from threading import Thread, Lock
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

# --- CONFIGURACIÓN DE HORARIOS ---
class HorarioBursatil:
    def __init__(self):
        self.ny_tz = pytz.timezone('America/New_York')
        self.col_tz = pytz.timezone('America/Bogota')
        self.utc_tz = pytz.timezone('UTC')
        
        # Feriados de USA
        self.us_holidays = holidays.US(years=datetime.now().year)
    
    def es_horario_bursatil_ny(self):
        """Verifica si es horario bursátil en NY (9:30-16:00 ET)"""
        ahora_ny = datetime.now(self.ny_tz)
        
        # Verificar si es fin de semana
        if ahora_ny.weekday() >= 5:
            return False
        
        # Verificar si es feriado
        if ahora_ny.date() in self.us_holidays:
            return False
        
        # Verificar horario
        hora_actual = ahora_ny.strftime('%H:%M')
        return '09:30' <= hora_actual <= '16:00'
    
    def es_horario_bursatil_col(self):
        """Verifica si es horario bursátil en Colombia (9:00-16:00 COT)"""
        ahora_col = datetime.now(self.col_tz)
        
        if ahora_col.weekday() >= 5:
            return False
        
        hora_actual = ahora_col.strftime('%H:%M')
        return '09:00' <= hora_actual <= '16:00'
    
    def obtener_info_mercados(self):
        """Obtiene estado de todos los mercados relevantes"""
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

# --- LISTAS OPTIMIZADAS SEGÚN TUS ESPECIFICACIONES ---

# 1. CRIPTOMONEDAS (RWA - Real World Assets con potencial)
CRYPTO_ACTIVOS = [
    ("BTC-USD", "Bitcoin", "🪙 Crypto - Store of Value"),
    ("ETH-USD", "Ethereum", "🪙 Crypto - Smart Contracts"),
    ("BNB-USD", "Binance Coin", "🪙 Crypto - Exchange Token"),
    ("ADA-USD", "Cardano", "🪙 Crypto - RWA Focus"),
    ("SOL-USD", "Solana", "🪙 Crypto - High Speed"),
    ("LINK-USD", "Chainlink", "🪙 Crypto - Oracle RWA"),
    ("AAVE-USD", "Aave", "🪙 Crypto - DeFi RWA"),
    ("MKR-USD", "MakerDAO", "🪙 Crypto - Stablecoin RWA"),
    ("COMP-USD", "Compound", "🪙 Crypto - Lending RWA"),
    ("SNX-USD", "Synthetix", "🪙 Crypto - Synthetic RWA")
]

# 2. COMMODITIES (Metales y Energía solamente)
COMMODITIES_ACTIVOS = [
    ("GC=F", "Oro", "🥇 Commodity - Metal Precioso"),
    ("SI=F", "Plata", "🥈 Commodity - Metal Precioso"),
    ("HG=F", "Cobre", "🔧 Commodity - Metal Industrial"),
    ("CL=F", "Petróleo Crudo", "🛢️ Commodity - Energía"),
    ("NG=F", "Gas Natural", "🔥 Commodity - Energía"),
    ("PA=F", "Paladio", "💎 Commodity - Metal Industrial")
]

# 3. ACCIONES COLOMBIANAS (Solo las que especificaste)
COLOMBIAN_ACTIVOS = [
    ("EC", "Ecopetrol", "🇨🇴 Colombia - Petróleo"),
    ("ISA", "Interconexión Eléctrica", "🇨🇴 Colombia - Energía")
]

# 4. ETFs (Solo XLF como solicitaste)
ETF_ACTIVOS = [
    ("XLF", "Financial Select Sector SPDR", "🏦 ETF - Sector Financiero")
]

# Función para obtener Penny Stocks dinámicos (sin lista predefinida)
def obtener_penny_stocks_dinamicos(limit=15):
    """Obtiene penny stocks en tiempo real de FMP según movimiento del mercado"""
    if not FMP_API_KEY:
        return []  # Sin lista predefinida
    
    try:
        # Filtros dinámicos para encontrar penny stocks con movimiento
        url = f"https://financialmodelingprep.com/api/v3/stock-screener?"
        url += f"marketCapLowerThan=1000000000&"      # Capitalización menor a 1B
        url += f"priceLowerThan=5&"                   # Precio menor a $5
        url += f"volumeMoreThan=2000000&"             # Volumen > 2M (actividad)
        url += f"changeMoreThan=5&"                   # Cambio > 5% (movimiento)
        url += f"exchange=NASDAQ,NYS&"               # NASDAQ y NYSE
        url += f"limit={limit}&"
        url += f"apikey={FMP_API_KEY}"
        
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data:
            # Ordenar por volumen (más activos primero)
            data_sorted = sorted(data, key=lambda x: x.get('volume', 0), reverse=True)
            
            return [(item['symbol'], 
                    item.get('companyName', 'Penny Stock')[:30], 
                    f"🎯 Penny Stock - Vol: {item.get('volume', 0):,}") 
                   for item in data_sorted[:8]]
        else:
            return []
            
    except Exception as e:
        print(f"Error obteniendo penny stocks: {e}")
        return []

# Función para obtener Penny Stocks por momentum
def obtener_penny_stocks_momentum(limit=10):
    """Obtiene penny stocks con alto momentum"""
    if not FMP_API_KEY:
        return []
    
    try:
        url = f"https://financialmodelingprep.com/api/v3/stock-screener?"
        url += f"priceLowerThan=10&"                   # Precio accesible
        url += f"volumeMoreThan=1000000&"             # Buen volumen
        url += f"changeMoreThan=8&"                   # Cambio > 8% (momentum)
        url += f"betaMoreThan=2&"                     # Alta volatilidad (beta > 2)
        url += f"exchange=NASDAQ,NYS,AMEX&"           # Todas las bolsas
        url += f"limit={limit}&"
        url += f"apikey={FMP_API_KEY}"
        
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data:
            return [(item['symbol'], 
                    item.get('companyName', 'Momentum Stock')[:25], 
                    f"🚀 Momentum - Cambio: {item.get('changesPercentage', 0):.1f}%") 
                   for item in data[:6]]
        else:
            return []
            
    except Exception as e:
        print(f"Error obteniendo penny stocks momentum: {e}")
        return []

# --- FUNCIONES DE ANÁLISIS MEJORADAS ---
def analizar_activo_avanzado(df, ticker):
    """Análisis técnico completo"""
    try:
        analysis = {}
        
        # Precios
        analysis['precio'] = float(df['Close'].iloc[-1])
        analysis['apertura'] = float(df['Open'].iloc[-1])
        analysis['alto'] = float(df['High'].iloc[-1])
        analysis['bajo'] = float(df['Low'].iloc[-1])
        analysis['volumen'] = int(df['Volume'].iloc[-1])
        
        # Indicadores técnicos
        analysis['rsi'] = ta.rsi(df['Close'], length=14).iloc[-1]
        
        macd = ta.macd(df['Close'])
        analysis['macd'] = macd['MACD_12_26_9'].iloc[-1]
        analysis['macd_signal'] = macd['MACDS_12_26_9'].iloc[-1]
        analysis['macd_hist'] = macd['MACDh_12_26_9'].iloc[-1]
        
        analysis['sma_20'] = ta.sma(df['Close'], length=20).iloc[-1]
        analysis['sma_50'] = ta.sma(df['Close'], length=50).iloc[-1]
        analysis['ema_12'] = ta.ema(df['Close'], length=12).iloc[-1]
        
        bbands = ta.bbands(df['Close'], length=20)
        analysis['bb_upper'] = bbands['BBU_20_2.0'].iloc[-1]
        analysis['bb_lower'] = bbands['BBL_20_2.0'].iloc[-1]
        analysis['bb_middle'] = bbands['BBM_20_2.0'].iloc[-1]
        
        # Volumen relativo
        vol_promedio = df['Volume'].rolling(20).mean().iloc[-1]
        analysis['vol_relativo'] = analysis['volumen'] / vol_promedio if vol_promedio > 0 else 1
        
        # Señales
        analysis['señal_rsi'] = "Sobreventa" if analysis['rsi'] < 30 else "Sobrecompra" if analysis['rsi'] > 70 else "Neutral"
        analysis['señal_macd'] = "Alcista" if analysis['macd'] > analysis['macd_signal'] else "Bajista"
        analysis['señal_tendencia'] = "Alcista" if analysis['precio'] > analysis['sma_20'] else "Bajista"
        analysis['señal_bb'] = "Sobrecomprado" if analysis['precio'] > analysis['bb_upper'] else "Sobreventa" if analysis['precio'] < analysis['bb_lower'] else "Normal"
        
        return analysis
    except Exception as e:
        print(f"Error en análisis avanzado {ticker}: {e}")
        return None

def obtener_sentimiento_noticias(ticker):
    """Obtiene sentimiento de noticias con múltiples fuentes"""
    if not FMP_API_KEY:
        return 0
    
    try:
        # Noticias recientes
        url = f"https://financialmodelingprep.com/api/v3/stock_news?tickers={ticker}&limit=10&apikey={FMP_API_KEY}"
        response = requests.get(url, timeout=10)
        news = response.json()
        
        if not news: 
            return 0
        
        # Análisis de sentimiento
        sentiment_score = 0
        titulos = []
        
        for item in news[:5]:
            titulo = item['title']
            titulos.append(titulo)
            
            analysis = TextBlob(titulo)
            polarity = analysis.sentiment.polarity
            
            # Ponderar palabras clave
            palabras_positivas = ['bullish', 'surge', 'jump', 'rally', 'gain', 'upgrade', 'beat']
            palabras_negativas = ['bearish', 'drop', 'fall', 'plunge', 'loss', 'downgrade', 'miss']
            
            titulo_lower = titulo.lower()
            if any(palabra in titulo_lower for palabra in palabras_positivas):
                polarity *= 1.3
            elif any(palabra in titulo_lower for palabra in palabras_negativas):
                polarity *= 1.3
            
            sentiment_score += polarity
        
        avg_sentiment = sentiment_score / len(news[:5]) if news[:5] else 0
        return avg_sentiment * 0.15
        
    except Exception as e:
        print(f"Error obteniendo sentimiento para {ticker}: {e}")
        return 0

def predecir_tendencia_ml(df, ticker, es_crypto=False, es_penny=False):
    """Predicción ML mejorada con ajustes por tipo de activo"""
    try:
        data = df.copy()
        
        # Preparar características
        data['Target'] = (data['Close'].shift(-1) > data['Close']).astype(int)
        
        # Indicadores técnicos
        data['RSI'] = ta.rsi(data['Close'], length=14)
        data['MACD'] = ta.macd(data['Close'])['MACD_12_26_9']
        data['SMA_20'] = ta.sma(data['Close'], length=20)
        data['SMA_50'] = ta.sma(data['Close'], length=50)
        data['Vol_Rel'] = data['Volume'] / data['Volume'].rolling(20).mean()
        
        # Momentum
        data['Momentum'] = data['Close'].pct_change(5)
        data['ROC'] = ta.roc(data['Close'], length=10)
        data['ADX'] = ta.adx(data['High'], data['Low'], data['Close'])['ADX_14']
        
        data = data.dropna()
        
        if len(data) < 40:
            return 0.5
        
        # Características para ML
        features = ['RSI', 'MACD', 'SMA_20', 'Vol_Rel', 'Momentum', 'ROC', 'ADX']
        X = data[features]
        y = data['Target']
        
        # Entrenar modelo
        model = RandomForestClassifier(
            n_estimators=100, 
            random_state=42, 
            max_depth=7,
            min_samples_split=5
        )
        
        # Usar datos históricos para entrenar
        train_size = int(len(X) * 0.8)
        X_train, y_train = X[:train_size], y[:train_size]
        
        model.fit(X_train, y_train)
        
        # Predecir el último dato
        prob_base = model.predict_proba(X.tail(1))[0][1]
        
        # Añadir sentimiento de noticias (excepto para penny stocks)
        sentimiento = 0
        if not es_penny:  # Para penny stocks no usamos sentimiento
            sentimiento = obtener_sentimiento_noticias(ticker)
        
        # Ajustar probabilidad según tipo de activo
        if es_crypto:
            # Crypto: más sensible a momentum
            prob_ajustada = prob_base * 1.1 + sentimiento
        elif es_penny:
            # Penny stocks: más conservador, solo análisis técnico
            prob_ajustada = prob_base * 0.9
        else:
            # Otros: balanceado
            prob_ajustada = prob_base + sentimiento
        
        # Limitar entre 0 y 1
        return max(0, min(1, prob_ajustada))
        
    except Exception as e:
        print(f"Error en ML para {ticker}: {e}")
        return 0.5

async def procesar_activo_completo(ticker, nombre, categoria, es_crypto=False, es_penny=False):
    """Procesa un activo con análisis completo"""
    print(f"🔍 Analizando: {ticker} ({nombre}) - {categoria}")
    
    try:
        # Configurar parámetros según tipo
        if es_crypto:
            interval = "15m"
            period = "7d"
            min_prob = 0.12  # Menos exigente con cryptos
            rsi_min, rsi_max = 25, 75  # Más flexible
        elif es_penny:
            interval = "30m"
            period = "1mo"
            min_prob = 0.20  # Más exigente con penny stocks (riesgo alto)
            rsi_min, rsi_max = 30, 70  # Estricto
        elif "Commodity" in categoria:
            interval = "1h"
            period = "3mo"
            min_prob = 0.15
            rsi_min, rsi_max = 30, 70
        else:
            interval = "1h"
            period = "1mo"
            min_prob = 0.15
            rsi_min, rsi_max = 30, 70
        
        # Descargar datos
        df = yf.download(ticker, period=period, interval=interval, 
                        progress=False, timeout=15)
        
        if df is None or df.empty or len(df) < 25:
            print(f"❌ {ticker}: Datos insuficientes")
            return
        
        if isinstance(df.columns, pd.MultiIndex): 
            df.columns = df.columns.get_level_values(0)
        
        # Análisis avanzado
        analisis = analizar_activo_avanzado(df, ticker)
        if not analisis:
            return
        
        # Predicción ML
        prob = predecir_tendencia_ml(df, ticker, es_crypto, es_penny)
        
        # CONDICIONES DE SEÑAL MEJORADAS
        condiciones = []
        señales = []
        
        # 1. Probabilidad ML (requerida)
        if prob >= min_prob:
            condiciones.append(True)
            señales.append(f"ML: {prob:.1%}")
        else:
            condiciones.append(False)
        
        # 2. RSI (rango saludable)
        if rsi_min <= analisis['rsi'] <= rsi_max:
            condiciones.append(True)
            señales.append(f"RSI: {analisis['rsi']:.1f}")
        else:
            condiciones.append(False)
        
        # 3. Volumen (actividad suficiente)
        if es_penny:
            vol_minimo = 1.5  # Más volumen para penny stocks
        else:
            vol_minimo = 1.2
        
        if analisis['vol_relativo'] >= vol_minimo:
            condiciones.append(True)
            señales.append(f"Vol: {analisis['vol_relativo']:.1f}x")
        else:
            condiciones.append(False)
        
        # 4. Tendencia alcista
        if analisis['señal_tendencia'] == "Alcista":
            condiciones.append(True)
            señales.append("Tend: ↑")
        else:
            condiciones.append(False)
        
        # 5. MACD (opcional para crypto, requerido para otros)
        if es_crypto:
            # Para crypto, MACD es opcional
            if analisis['señal_macd'] == "Alcista":
                condiciones.append(True)
                señales.append("MACD: ↑")
        else:
            # Para otros, requerido
            if analisis['señal_macd'] == "Alcista":
                condiciones.append(True)
                señales.append("MACD: ↑")
            else:
                condiciones.append(False)
        
        # CALCULAR REQUISITOS
        if es_crypto:
            # Crypto: 3 de 4 condiciones principales
            condiciones_principales = condiciones[:4]
            requiere_señal = sum(condiciones_principales) >= 3
        elif es_penny:
            # Penny stocks: 4 de 5 condiciones (más estricto)
            requiere_señal = sum(condiciones) >= 4
        else:
            # Otros: 4 de 5 condiciones
            requiere_señal = sum(condiciones) >= 4
        
        if requiere_señal:
            # GENERAR SEÑAL
            precio = analisis['precio']
            
            # Determinar emoji y color según categoría
            if es_crypto:
                emoji = "🪙"
                color = "#FFD700"  # Dorado
            elif es_penny:
                emoji = "🎯"
                color = "#FF6B6B"  # Rojo
            elif "Commodity" in categoria:
                emoji = "📊"
                color = "#4ECDC4"  # Turquesa
            elif "Colombia" in categoria:
                emoji = "🇨🇴"
                color = "#FECA57"  # Amarillo
            elif "ETF" in categoria:
                emoji = "📈"
                color = "#54A0FF"  # Azul
            else:
                emoji = "🏢"
                color = "#00D2D3"  # Verde
            
            # Crear mensaje detallado
            msg = (f"{emoji} **SEÑAL DETECTADA**\n"
                  f"Activo: `{ticker}`\n"
                  f"Nombre: {nombre}\n"
                  f"Categoría: {categoria}\n"
                  f"Precio: ${precio:.2f}\n"
                  f"Probabilidad IA: {prob:.1%}\n"
                  f"Señales: {', '.join(señales)}\n"
                  f"RSI: {analisis['rsi']:.1f} ({analisis['señal_rsi']})\n"
                  f"MACD: {analisis['señal_macd']}\n"
                  f"Volumen: {analisis['vol_relativo']:.1f}x promedio\n"
                  f"Hora: {datetime.now().strftime('%H:%M')}")
            
            await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')
            print(f"✅ Señal enviada para {ticker} ({prob:.1%})")
            
        else:
            print(f"❌ {ticker} no cumple condiciones suficientes")
            print(f"   Condiciones: {condiciones}")
            print(f"   Prob: {prob:.1%}, RSI: {analisis['rsi']:.1f}")
            
    except Exception as e:
        print(f"Error procesando {ticker}: {e}")

# --- BUCLE PRINCIPAL OPTIMIZADO ---
async def main_loop_optimizado():
    """Bucle principal optimizado según tus especificaciones"""
    print("🤖 INVESTFRED AI - CONFIGURACIÓN OPTIMIZADA")
    print("=" * 60)
    
    ciclo = 0
    
    while True:
        try:
            ciclo += 1
            ahora = datetime.now()
            
            # Obtener info de mercados
            mercados = horario.obtener_info_mercados()
            
            # Determinar qué analizar
            es_horario_ny = mercados['ny_abierto']
            es_horario_col = mercados['col_abierto']
            
            print(f"\n🔄 CICLO #{ciclo} - {ahora.strftime('%Y-%m-%d %H:%M')}")
            print(f"📍 NY: {mercados['hora_ny']} ({'ABIERTO' if es_horario_ny else 'CERRADO'})")
            print(f"📍 CO: {mercados['hora_col']} ({'ABIERTO' if es_horario_col else 'CERRADO'})")
            
            # CONSTRUIR LISTA DE ACTIVOS A ANALIZAR
            activos_a_analizar = []
            
            # 1. CRIPTOMONEDAS RWA (SIEMPRE, 24/7)
            print(f"➕ Añadiendo {len(CRYPTO_ACTIVOS)} criptomonedas RWA...")
            activos_a_analizar.extend([(*activo, True, False) for activo in CRYPTO_ACTIVOS])
            
            # 2. COMMODITIES (Metales y Energía)
            if es_horario_ny:
                print(f"➕ Añadiendo commodities (Oro, Plata, Cobre, Petróleo)...")
                activos_a_analizar.extend([(*activo, False, False) for activo in COMMODITIES_ACTIVOS])
            
            # 3. ACCIONES COLOMBIANAS (EC y ISA)
            if es_horario_col or es_horario_ny:
                print(f"➕ Añadiendo acciones Colombianas (EC, ISA)...")
                activos_a_analizar.extend([(*activo, False, False) for activo in COLOMBIAN_ACTIVOS])
            
            # 4. PENNY STOCKS DINÁMICOS (Solo en horario NY)
            if es_horario_ny and FMP_API_KEY:
                print(f"➕ Buscando Penny Stocks dinámicos...")
                
                # Obtener penny stocks por volumen (cada ciclo)
                penny_volumen = obtener_penny_stocks_dinamicos(limit=10)
                activos_a_analizar.extend([(*activo, False, True) for activo in penny_volumen])
                
                # Obtener penny stocks por momentum (cada 2 ciclos)
                if ciclo % 2 == 0:
                    penny_momentum = obtener_penny_stocks_momentum(limit=6)
                    activos_a_analizar.extend([(*activo, False, True) for activo in penny_momentum])
            
            # 5. ETF XLF (Solo en horario NY)
            if es_horario_ny:
                print(f"➕ Añadiendo ETF XLF...")
                activos_a_analizar.extend([(*activo, False, False) for activo in ETF_ACTIVOS])
            
            # Eliminar duplicados manteniendo el primero
            seen = set()
            activos_unicos = []
            for activo in activos_a_analizar:
                ticker = activo[0]
                if ticker not in seen:
                    seen.add(ticker)
                    activos_unicos.append(activo)
            
            print(f"📊 TOTAL ACTIVOS ÚNICOS A ANALIZAR: {len(activos_unicos)}")
            
            # ANALIZAR ACTIVOS
            for ticker, nombre, categoria, es_crypto, es_penny in activos_unicos:
                await procesar_activo_completo(ticker, nombre, categoria, es_crypto, es_penny)
                await asyncio.sleep(1.5)
            
            # CALCULAR TIEMPO DE ESPERA INTELIGENTE
            if es_horario_ny:
                wait_time = 1200  # 20 minutos en horario activo
            elif es_horario_col and not es_horario_ny:
                wait_time = 1800  # 30 minutos si solo Colombia abierto
            else:
                wait_time = 2400  # 40 minutos fuera de horario (más cryptos)
            
            # Enviar resumen cada 4 ciclos
            if ciclo % 4 == 0:
                msg_resumen = (f"📋 **RESUMEN CICLO #{ciclo}**\n"
                              f"Activos analizados: {len(activos_unicos)}\n"
                              f"Mercado NY: {'✅ Abierto' if es_horario_ny else '❌ Cerrado'}\n"
                              f"Mercado CO: {'✅ Abierto' if es_horario_col else '❌ Cerrado'}\n"
                              f"Penny Stocks encontrados: {sum(1 for a in activos_unicos if a[4])}\n"
                              f"Criptos RWA analizadas: {sum(1 for a in activos_unicos if a[3])}\n"
                              f"Próximo ciclo en: {wait_time//60} minutos\n"
                              f"Hora: {datetime.now().strftime('%H:%M')}")
                
                await bot.send_message(chat_id=CHAT_ID, text=msg_resumen, parse_mode='Markdown')
            
            print(f"✅ Ciclo #{ciclo} completado. Esperando {wait_time//60} minutos...")
            print(f"⏰ Próximo ciclo: {(datetime.now() + timedelta(seconds=wait_time)).strftime('%H:%M')}")
            print("=" * 60)
            
            await asyncio.sleep(wait_time)
            
        except Exception as e:
            print(f"Error en ciclo #{ciclo}: {e}")
            await asyncio.sleep(300)

# --- SERVIDOR WEB ---
app = Flask('')
@app.route('/')
def home():
    mercados = horario.obtener_info_mercados()
    return f"""
    <html>
    <head><title>INVESTFRED AI</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        h1 {{ color: #2c3e50; }}
        .container {{ max-width: 800px; margin: 0 auto; }}
        .status {{ padding: 15px; margin: 10px 0; border-radius: 8px; }}
        .open {{ background-color: #d4edda; border: 1px solid #c3e6cb; }}
        .closed {{ background-color: #f8d7da; border: 1px solid #f5c6cb; }}
        .assets {{ background-color: #e2e3e5; padding: 15px; border-radius: 8px; }}
        ul {{ list-style-type: none; padding: 0; }}
        li {{ padding: 5px 0; }}
    </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 INVESTFRED AI - Configuración Optimizada</h1>
            
            <div class="status {'open' if mercados['ny_abierto'] else 'closed'}">
                <h3>📊 Estado de Mercados</h3>
                <p><strong>NYSE/NASDAQ:</strong> {mercados['hora_ny']} ({'✅ ABIERTO' if mercados['ny_abierto'] else '🔴 CERRADO'})</p>
                <p><strong>BVC Colombia:</strong> {mercados['hora_col']} ({'✅ ABIERTO' if mercados['col_abierto'] else '🔴 CERRADO'})</p>
                <p><strong>Día:</strong> {mercados['dia_semana']}</p>
            </div>
            
            <div class="assets">
                <h3>🎯 Activos Monitoreados</h3>
                <ul>
                    <li>🪙 <strong>Criptomonedas RWA:</strong> BTC, ETH, BNB, ADA, SOL, LINK, AAVE, MKR, COMP, SNX</li>
                    <li>🥇 <strong>Commodities:</strong> Oro (GC=F), Plata (SI=F), Cobre (HG=F), Petróleo (CL=F), Gas (NG=F), Paladio (PA=F)</li>
                    <li>🇨🇴 <strong>Colombia:</strong> Ecopetrol (EC), ISA</li>
                    <li>🎯 <strong>Penny Stocks:</strong> Dinámicos según movimiento del mercado</li>
                    <li>📈 <strong>ETF:</strong> XLF (Sector Financiero)</li>
                </ul>
            </div>
            
            <p><em>El bot analiza automáticamente según horario bursátil</em></p>
        </div>
    </body>
    </html>
    """

@app.route('/activos')
def lista_activos():
    return json.dumps({
        "criptos_rwa": CRYPTO_ACTIVOS,
        "commodities": COMMODITIES_ACTIVOS,
        "colombia": COLOMBIAN_ACTIVOS,
        "etfs": ETF_ACTIVOS,
        "penny_stocks": "Dinámicos según movimiento del mercado"
    }, indent=2)

def run_web():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)

# --- INICIO OPTIMIZADO ---
async def inicio_optimizado():
    """Secuencia de inicio optimizada"""
    try:
        mercados = horario.obtener_info_mercados()
        
        msg = (f"🚀 **INVESTFRED AI - CONFIGURACIÓN OPTIMIZADA INICIADA**\n\n"
               f"📅 **HORARIOS:**\n"
               f"• NY: {mercados['hora_ny']} ({'✅ ABIERTO' if mercados['ny_abierto'] else '⏸️ CERRADO'})\n"
               f"• CO: {mercados['hora_col']} ({'✅ ABIERTO' if mercados['col_abierto'] else '⏸️ CERRADO'})\n"
               f"• Día: {mercados['dia_semana']}\n\n"
               f"🎯 **ACTIVOS CONFIGURADOS:**\n"
               f"• 🪙 Criptos RWA (10): BTC, ETH, BNB, ADA, SOL, LINK, AAVE, MKR, COMP, SNX\n"
               f"• 📊 Commodities (6): Oro, Plata, Cobre, Petróleo, Gas, Paladio\n"
               f"• 🇨🇴 Colombia (2): Ecopetrol (EC), ISA\n"
               f"• 🎯 Penny Stocks: Dinámicos según movimiento del mercado\n"
               f"• 📈 ETF: XLF (Sector Financiero)\n\n"
               f"⚙️ **CONFIGURACIÓN ESPECIAL:**\n"
               f"• Penny Stocks: Solo en horario NY, búsqueda dinámica\n"
               f"• Criptos RWA: Análisis 24/7, enfoque en Real World Assets\n"
               f"• Commodities: Metales y energía durante horario NY\n"
               f"• Análisis: ML + Sentimiento + Técnico\n\n"
               f"🔔 **Señales cuando se cumplan condiciones técnicas.**")
        
        await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')
        print("✅ Mensaje de inicio enviado con configuración optimizada")
        
    except Exception as e:
        print(f"❌ Error en inicio: {e}")

# --- PUNTO DE ENTRADA ---
if __name__ == "__main__":
    print("=" * 60)
    print("🤖 INVESTFRED AI - CONFIGURACIÓN OPTIMIZADA")
    print("=" * 60)
    
    print("\n🎯 CONFIGURACIÓN ESPECÍFICA:")
    print("• CRIPTO RWA: BTC, ETH, BNB, ADA, SOL, LINK, AAVE, MKR, COMP, SNX")
    print("• COMMODITIES: Oro (GC=F), Plata (SI=F), Cobre (HG=F), Petróleo (CL=F), Gas (NG=F), Paladio (PA=F)")
    print("• COLOMBIA: EC (Ecopetrol), ISA")
    print("• PENNY STOCKS: Búsqueda dinámica según movimiento (sin lista fija)")
    print("• ETF: XLF (Financial Sector)")
    print("• HORARIO: Automático según NY y Colombia")
    print("=" * 60)
    
    # Verificar variables
    if not TOKEN or not CHAT_ID:
        print("❌ ERROR: Faltan telegram_token o chat_ID")
        exit(1)
    
    # Iniciar servidor web
    Thread(target=run_web, daemon=True).start()
    print("🌐 Servidor web iniciado en puerto 8080")
    
    # Ejecutar bot
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Inicio optimizado
        loop.run_until_complete(inicio_optimizado())
        time.sleep(3)
        
        # Bucle principal optimizado
        print("\n🔄 Iniciando ciclo principal optimizado...")
        loop.run_until_complete(main_loop_optimizado())
        
    except KeyboardInterrupt:
        print("\n🛑 Bot detenido manualmente")
    except Exception as e:
        print(f"💥 Error crítico: {e}")
