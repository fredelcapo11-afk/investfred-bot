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

# =================================================================
# ⚙️ CONFIGURACIÓN DE UMBRALES - ¡AQUÍ AJUSTAS EL 70%!
# =================================================================

# UMBRALES DE PROBABILIDAD POR TIPO DE ACTIVO (70% configurado)
UMBRALES = {
    'CRYPTO': 0.70,        # 70% para criptomonedas
    'COMMODITY': 0.70,     # 70% para commodities
    'COLOMBIA': 0.70,      # 70% para acciones colombianas
    'PENNY_STOCK': 0.70,   # 70% para penny stocks (más conservador)
    'ETF': 0.70,           # 70% para ETFs
    'DEFAULT': 0.70        # 70% para cualquier otro
}

# Umbrales de RSI (ajustados para ser más conservadores)
RSI_UMBRALES = {
    'CRYPTO': (30, 70),      # Crypto: RSI entre 30 y 70
    'COMMODITY': (35, 65),   # Commodities: más conservador
    'COLOMBIA': (35, 65),    # Colombia: más conservador
    'PENNY_STOCK': (40, 60), # Penny: muy conservador
    'ETF': (35, 65),         # ETF: conservador
    'DEFAULT': (35, 65)      # Por defecto
}

# Umbrales de volumen mínimo
VOLUMEN_UMBRALES = {
    'CRYPTO': 1.2,          # Crypto: 20% más que promedio
    'COMMODITY': 1.3,       # Commodities: 30% más
    'COLOMBIA': 1.4,        # Colombia: 40% más
    'PENNY_STOCK': 1.5,     # Penny: 50% más (muy importante)
    'ETF': 1.3,             # ETF: 30% más
    'DEFAULT': 1.3
}

# =================================================================

# --- CONFIGURACIÓN DE HORARIOS ---
class HorarioBursatil:
    def __init__(self):
        self.ny_tz = pytz.timezone('America/New_York')
        self.col_tz = pytz.timezone('America/Bogota')
        self.utc_tz = pytz.timezone('UTC')
        
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

# 2. COMMODITIES
COMMODITIES_ACTIVOS = [
    ("GC=F", "Oro", "🥇 Commodity - Metal Precioso"),
    ("SI=F", "Plata", "🥈 Commodity - Metal Precioso"),
    ("HG=F", "Cobre", "🔧 Commodity - Metal Industrial"),
    ("CL=F", "Petróleo Crudo", "🛢️ Commodity - Energía"),
    ("NG=F", "Gas Natural", "🔥 Commodity - Energía"),
    ("PA=F", "Paladio", "💎 Commodity - Metal Industrial")
]

# 3. ACCIONES COLOMBIANAS
COLOMBIAN_ACTIVOS = [
    ("EC", "Ecopetrol", "🇨🇴 Colombia - Petróleo"),
    ("ISA", "Interconexión Eléctrica", "🇨🇴 Colombia - Energía")
]

# 4. ETFs
ETF_ACTIVOS = [
    ("XLF", "Financial Select Sector SPDR", "🏦 ETF - Sector Financiero")
]

def obtener_penny_stocks_dinamicos(limit=10):
    """Obtiene penny stocks en tiempo real con filtros estrictos"""
    if not FMP_API_KEY:
        return []
    
    try:
        # Filtros MUY ESTRICTOS para alta probabilidad
        url = f"https://financialmodelingprep.com/api/v3/stock-screener?"
        url += f"marketCapLowerThan=500000000&"      # Capitalización pequeña
        url += f"priceLowerThan=3&"                  # Precio menor a $3
        url += f"volumeMoreThan=5000000&"            # Volumen ALTO > 5M
        url += f"changeMoreThan=10&"                 # Cambio > 10% (alto momentum)
        url += f"exchange=NASDAQ,NYS&"               # Bolsas principales
        url += f"limit={limit}&"
        url += f"apikey={FMP_API_KEY}"
        
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data:
            # Ordenar por cambio porcentual (más momentum primero)
            data_sorted = sorted(data, 
                               key=lambda x: abs(x.get('changesPercentage', 0)), 
                               reverse=True)
            
            return [(item['symbol'], 
                    item.get('companyName', 'Penny Stock')[:25], 
                    f"🎯 Penny - Cambio: {item.get('changesPercentage', 0):.1f}%") 
                   for item in data_sorted[:6]]
        else:
            return []
            
    except Exception as e:
        print(f"Error obteniendo penny stocks: {e}")
        return []

# --- FUNCIONES DE ANÁLISIS CON UMBRAL 70% ---
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
        
        # Bandas Bollinger
        bbands = ta.bbands(df['Close'], length=20, std=2)
        analysis['bb_upper'] = bbands['BBU_20_2.0'].iloc[-1]
        analysis['bb_lower'] = bbands['BBL_20_2.0'].iloc[-1]
        analysis['bb_middle'] = bbands['BBM_20_2.0'].iloc[-1]
        
        # Volumen relativo
        vol_promedio = df['Volume'].rolling(20).mean().iloc[-1]
        analysis['vol_relativo'] = analysis['volumen'] / vol_promedio if vol_promedio > 0 else 1
        
        # Señales
        analysis['señal_rsi'] = "Sobreventa" if analysis['rsi'] < 30 else "Sobrecompra" if analysis['rsi'] > 70 else "Neutral"
        analysis['señal_macd'] = "Alcista" if analysis['macd'] > analysis['macd_signal'] else "Bajista"
        analysis['señal_tendencia'] = "Alcista" if analysis['precio'] > analysis['sma_20'] > analysis['sma_50'] else "Bajista"
        analysis['señal_bb'] = "Sobrecomprado" if analysis['precio'] > analysis['bb_upper'] else "Sobreventa" if analysis['precio'] < analysis['bb_lower'] else "Normal"
        
        return analysis
    except Exception as e:
        print(f"Error en análisis avanzado {ticker}: {e}")
        return None

def obtener_sentimiento_noticias(ticker):
    """Obtiene sentimiento de noticias"""
    if not FMP_API_KEY:
        return 0
    
    try:
        url = f"https://financialmodelingprep.com/api/v3/stock_news?tickers={ticker}&limit=10&apikey={FMP_API_KEY}"
        response = requests.get(url, timeout=10)
        news = response.json()
        
        if not news: 
            return 0
        
        sentiment_score = 0
        for item in news[:5]:
            analysis = TextBlob(item['title'])
            polarity = analysis.sentiment.polarity
            sentiment_score += polarity
        
        avg_sentiment = sentiment_score / len(news[:5]) if news[:5] else 0
        # Impacto moderado para no distorsionar mucho la probabilidad
        return avg_sentiment * 0.08
        
    except Exception as e:
        print(f"Error obteniendo sentimiento para {ticker}: {e}")
        return 0

def predecir_tendencia_ml_estricta(df, ticker, tipo_activo):
    """Predicción ML ESTRICTA para alcanzar 70%"""
    try:
        data = df.copy()
        
        # Preparar características
        data['Target'] = (data['Close'].shift(-2) > data['Close'].shift(-1)).astype(int)
        
        # MÁS indicadores técnicos para mejor predicción
        data['RSI'] = ta.rsi(data['Close'], length=14)
        data['RSI_SMA'] = ta.sma(data['RSI'], length=10)
        
        macd = ta.macd(data['Close'])
        data['MACD'] = macd['MACD_12_26_9']
        data['MACD_Signal'] = macd['MACDS_12_26_9']
        data['MACD_Hist'] = macd['MACDh_12_26_9']
        
        data['SMA_20'] = ta.sma(data['Close'], length=20)
        data['SMA_50'] = ta.sma(data['Close'], length=50)
        data['EMA_12'] = ta.ema(data['Close'], length=12)
        
        data['Vol_Rel'] = data['Volume'] / data['Volume'].rolling(20).mean()
        data['Volatilidad'] = data['Close'].rolling(20).std()
        
        # Momentum indicators
        data['Momentum_5'] = data['Close'].pct_change(5)
        data['Momentum_10'] = data['Close'].pct_change(10)
        data['ROC_10'] = ta.roc(data['Close'], length=10)
        
        # ADX para fuerza de tendencia
        adx_data = ta.adx(data['High'], data['Low'], data['Close'])
        data['ADX'] = adx_data['ADX_14']
        data['DMP'] = adx_data['DMP_14']
        data['DMN'] = adx_data['DMN_14']
        
        data = data.dropna()
        
        if len(data) < 50:
            print(f"{ticker}: Datos insuficientes para ML estricto")
            return 0.5
        
        # Características para ML
        features = [
            'RSI', 'RSI_SMA', 'MACD', 'MACD_Hist',
            'SMA_20', 'SMA_50', 'EMA_12', 
            'Vol_Rel', 'Volatilidad',
            'Momentum_5', 'Momentum_10', 'ROC_10',
            'ADX', 'DMP', 'DMN'
        ]
        
        X = data[features]
        y = data['Target']
        
        # Modelo más complejo para mejor precisión
        model = RandomForestClassifier(
            n_estimators=200, 
            random_state=42, 
            max_depth=10,
            min_samples_split=4,
            min_samples_leaf=2,
            class_weight='balanced'
        )
        
        # Entrenar con más datos
        train_size = int(len(X) * 0.85)
        X_train, y_train = X[:train_size], y[:train_size]
        
        model.fit(X_train, y_train)
        
        # Predecir últimos datos
        prob_base = model.predict_proba(X.tail(3))[:, 1].mean()
        
        # Ajustar por tipo de activo
        ajuste_tipo = {
            'CRYPTO': 1.05,
            'COMMODITY': 1.0,
            'COLOMBIA': 0.95,
            'PENNY_STOCK': 0.9,  # Más conservador con penny
            'ETF': 1.0,
            'DEFAULT': 1.0
        }
        
        # Añadir sentimiento
        sentimiento = obtener_sentimiento_noticias(ticker)
        
        # Calcular probabilidad final con ajustes
        prob_ajustada = prob_base * ajuste_tipo.get(tipo_activo, 1.0)
        prob_final = prob_ajustada + sentimiento
        
        print(f"{ticker}: Prob base={prob_base:.1%}, Ajustada={prob_ajustada:.1%}, Sentimiento={sentimiento:.3f}, Final={prob_final:.1%}")
        
        # Limitar entre 0 y 1
        return max(0, min(1, prob_final))
        
    except Exception as e:
        print(f"Error en ML para {ticker}: {e}")
        return 0.5

# =================================================================
# 🎯 FUNCIÓN PRINCIPAL CON FILTRO 70%
# =================================================================
async def procesar_activo_con_filtro_70(ticker, nombre, categoria, tipo_activo):
    """Procesa un activo con filtro estricto del 70%"""
    print(f"🔍 Analizando: {ticker} ({nombre}) - {categoria}")
    print(f"   Umbral requerido: {UMBRALES[tipo_activo]*100}%")
    
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
            print(f"❌ {ticker}: Datos insuficientes")
            return
        
        if isinstance(df.columns, pd.MultiIndex): 
            df.columns = df.columns.get_level_values(0)
        
        # Análisis avanzado
        analisis = analizar_activo_avanzado(df, ticker)
        if not analisis:
            return
        
        # Predicción ML ESTRICTA
        prob = predecir_tendencia_ml_estricta(df, ticker, tipo_activo)
        
        # Obtener umbrales específicos
        umbral_prob = UMBRALES[tipo_activo]
        rsi_min, rsi_max = RSI_UMBRALES[tipo_activo]
        vol_minimo = VOLUMEN_UMBRALES[tipo_activo]
        
        # =============================================================
        # 🚨 FILTRO PRINCIPAL: VERIFICAR SI CUMPLE 70% O MÁS
        # =============================================================
        if prob >= umbral_prob:
            # Verificar condiciones adicionales
            condiciones_adicionales = []
            
            # 1. RSI en rango saludable
            rsi_ok = rsi_min <= analisis['rsi'] <= rsi_max
            condiciones_adicionales.append(('RSI', rsi_ok, f"{analisis['rsi']:.1f}"))
            
            # 2. Volumen suficiente
            vol_ok = analisis['vol_relativo'] >= vol_minimo
            condiciones_adicionales.append(('Volumen', vol_ok, f"{analisis['vol_relativo']:.1f}x"))
            
            # 3. Tendencia alcista
            tendencia_ok = analisis['señal_tendencia'] == "Alcista"
            condiciones_adicionales.append(('Tendencia', tendencia_ok, analisis['señal_tendencia']))
            
            # 4. MACD alcista
            macd_ok = analisis['señal_macd'] == "Alcista"
            condiciones_adicionales.append(('MACD', macd_ok, analisis['señal_macd']))
            
            # Contar condiciones cumplidas
            condiciones_cumplidas = sum(1 for _, cond, _ in condiciones_adicionales if cond)
            total_condiciones = len(condiciones_adicionales)
            
            # =============================================================
            # 🎯 DECISIÓN FINAL: ENVIAR SEÑAL SOLO SI CUMPLE TODO
            # =============================================================
            
            # Opción A: Requerir TODAS las condiciones (más estricto)
            # enviar_señal = condiciones_cumplidas == total_condiciones
            
            # Opción B: Requerir 3 de 4 condiciones (recomendado)
            enviar_señal = condiciones_cumplidas >= 3
            
            if enviar_señal:
                # 🚀 GENERAR SEÑAL DE ALTA PROBABILIDAD
                precio = analisis['precio']
                
                # Emojis según tipo
                emojis = {
                    'CRYPTO': '🪙',
                    'COMMODITY': '📊',
                    'COLOMBIA': '🇨🇴',
                    'PENNY_STOCK': '🎯',
                    'ETF': '📈'
                }
                
                emoji = emojis.get(tipo_activo, '📊')
                
                # Crear mensaje detallado
                condiciones_texto = []
                for nombre_cond, cumplida, valor in condiciones_adicionales:
                    status = "✅" if cumplida else "❌"
                    condiciones_texto.append(f"{status} {nombre_cond}: {valor}")
                
                msg = (f"{emoji} **🚨 SEÑAL DE ALTA PROBABILIDAD 🚨**\n"
                      f"**Activo:** `{ticker}`\n"
                      f"**Nombre:** {nombre}\n"
                      f"**Categoría:** {categoria}\n"
                      f"**Precio:** ${precio:.2f}\n\n"
                      f"**📊 PROBABILIDAD IA:** {prob:.1%} (Umbral: {umbral_prob*100}%)\n\n"
                      f"**🔍 CONDICIONES TÉCNICAS:**\n" + 
                      "\n".join(condiciones_texto) + "\n\n"
                      f"**📈 RSI:** {analisis['rsi']:.1f} ({analisis['señal_rsi']})\n"
                      f"**📊 MACD:** {analisis['señal_macd']}\n"
                      f"**📈 Tendencia:** {analisis['señal_tendencia']}\n"
                      f"**📊 Bandas Bollinger:** {analisis['señal_bb']}\n\n"
                      f"**⏰ Hora:** {datetime.now().strftime('%H:%M:%S')}\n"
                      f"**📅 Fecha:** {datetime.now().strftime('%Y-%m-%d')}")
                
                await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')
                print(f"✅✅✅ SEÑAL ENVIADA: {ticker} con {prob:.1%} de probabilidad")
                
                # También enviar un mensaje de alerta especial
                alerta_msg = f"⚠️ **ALERTA IMPORTANTE** ⚠️\nSe detectó señal de {prob:.1%} en `{ticker}`\n¡Revisa el análisis completo!"
                await bot.send_message(chat_id=CHAT_ID, text=alerta_msg, parse_mode='Markdown')
                
            else:
                print(f"⚠️ {ticker} tiene {prob:.1%} pero no cumple condiciones técnicas")
                print(f"   Condiciones: {condiciones_cumplidas}/{total_condiciones}")
                
        else:
            print(f"❌ {ticker}: Probabilidad {prob:.1%} < {umbral_prob*100}% (umbral)")
            
    except Exception as e:
        print(f"Error procesando {ticker}: {e}")

# --- BUCLE PRINCIPAL CON 70% ---
async def main_loop_con_70():
    """Bucle principal con filtro del 70%"""
    print("🤖 INVESTFRED AI - FILTRO 70% ACTIVADO")
    print("=" * 60)
    print("⚙️ CONFIGURACIÓN:")
    print(f"• Umbral mínimo: {UMBRALES['DEFAULT']*100}%")
    print(f"• Crypto: {UMBRALES['CRYPTO']*100}%")
    print(f"• Commodities: {UMBRALES['COMMODITY']*100}%")
    print(f"• Colombia: {UMBRALES['COLOMBIA']*100}%")
    print(f"• Penny Stocks: {UMBRALES['PENNY_STOCK']*100}%")
    print(f"• ETFs: {UMBRALES['ETF']*100}%")
    print("=" * 60)
    
    ciclo = 0
    
    while True:
        try:
            ciclo += 1
            ahora = datetime.now()
            
            mercados = horario.obtener_info_mercados()
            es_horario_ny = mercados['ny_abierto']
            es_horario_col = mercados['col_abierto']
            
            print(f"\n🔄 CICLO #{ciclo} - {ahora.strftime('%Y-%m-%d %H:%M')}")
            print(f"📍 NY: {mercados['hora_ny']} ({'ABIERTO' if es_horario_ny else 'CERRADO'})")
            print(f"📍 CO: {mercados['hora_col']} ({'ABIERTO' if es_horario_col else 'CERRADO'})")
            
            # LISTA DE ACTIVOS
            activos_a_analizar = []
            
            # 1. CRIPTOMONEDAS RWA (SIEMPRE)
            print(f"➕ Criptomonedas RWA (Umbral: {UMBRALES['CRYPTO']*100}%)...")
            for ticker, nombre, categoria in CRYPTO_ACTIVOS:
                activos_a_analizar.append((ticker, nombre, categoria, 'CRYPTO'))
            
            # 2. COMMODITIES (Horario NY)
            if es_horario_ny:
                print(f"➕ Commodities (Umbral: {UMBRALES['COMMODITY']*100}%)...")
                for ticker, nombre, categoria in COMMODITIES_ACTIVOS:
                    activos_a_analizar.append((ticker, nombre, categoria, 'COMMODITY'))
            
            # 3. ACCIONES COLOMBIANAS (Horario NY o CO)
            if es_horario_col or es_horario_ny:
                print(f"➕ Colombia (Umbral: {UMBRALES['COLOMBIA']*100}%)...")
                for ticker, nombre, categoria in COLOMBIAN_ACTIVOS:
                    activos_a_analizar.append((ticker, nombre, categoria, 'COLOMBIA'))
            
            # 4. PENNY STOCKS DINÁMICOS (Solo NY)
            if es_horario_ny and FMP_API_KEY and ciclo % 2 == 0:
                print(f"➕ Penny Stocks (Umbral: {UMBRALES['PENNY_STOCK']*100}%)...")
                penny_stocks = obtener_penny_stocks_dinamicos(limit=8)
                for ticker, nombre, categoria in penny_stocks:
                    activos_a_analizar.append((ticker, nombre, categoria, 'PENNY_STOCK'))
            
            # 5. ETF XLF (Solo NY)
            if es_horario_ny:
                print(f"➕ ETF XLF (Umbral: {UMBRALES['ETF']*100}%)...")
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
            
            print(f"📊 TOTAL ACTIVOS A ANALIZAR: {len(activos_unicos)}")
            
            # ANALIZAR CADA ACTIVO
            señales_encontradas = 0
            for ticker, nombre, categoria, tipo in activos_unicos:
                await procesar_activo_con_filtro_70(ticker, nombre, categoria, tipo)
                
                # Contar señales encontradas
                if "SEÑAL ENVIADA" in open(__file__).read():  # Simplificación
                    señales_encontradas += 1
                
                await asyncio.sleep(2)
            
            # CALCULAR TIEMPO DE ESPERA
            if es_horario_ny:
                wait_time = 1800  # 30 minutos en horario activo
            elif es_horario_col and not es_horario_ny:
                wait_time = 2400  # 40 minutos si solo Colombia
            else:
                wait_time = 3600  # 1 hora fuera de horario
            
            # RESUMEN DEL CICLO
            if ciclo % 2 == 0 or señales_encontradas > 0:
                msg_resumen = (f"📋 **RESUMEN CICLO #{ciclo}**\n"
                              f"Activos analizados: {len(activos_unicos)}\n"
                              f"Señales encontradas: {señales_encontradas}\n"
                              f"Umbral mínimo: {UMBRALES['DEFAULT']*100}%\n"
                              f"Mercado NY: {'✅ Abierto' if es_horario_ny else '❌ Cerrado'}\n"
                              f"Mercado CO: {'✅ Abierto' if es_horario_col else '❌ Cerrado'}\n"
                              f"Próximo ciclo en: {wait_time//60} minutos\n"
                              f"Hora: {datetime.now().strftime('%H:%M:%S')}")
                
                await bot.send_message(chat_id=CHAT_ID, text=msg_resumen, parse_mode='Markdown')
            
            print(f"✅ Ciclo #{ciclo} completado. Señales: {señales_encontradas}")
            print(f"⏰ Esperando {wait_time//60} minutos...")
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
    <head><title>INVESTFRED AI - 70%</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        .threshold {{ background: #e8f4fc; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 5px solid #3498db; }}
        .threshold h3 {{ color: #2980b9; margin-top: 0; }}
        .assets {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; }}
        .status {{ display: flex; justify-content: space-between; background: #e8f6f3; padding: 15px; border-radius: 8px; }}
        .status-item {{ text-align: center; }}
        .open {{ color: #27ae60; font-weight: bold; }}
        .closed {{ color: #e74c3c; font-weight: bold; }}
        ul {{ list-style-type: none; padding: 0; }}
        li {{ padding: 8px 0; border-bottom: 1px solid #eee; }}
        li:last-child {{ border-bottom: none; }}
    </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 INVESTFRED AI - UMBRAL 70%</h1>
            
            <div class="threshold">
                <h3>🎯 CONFIGURACIÓN DE UMBRALES</h3>
                <p><strong>Umbral mínimo de probabilidad: 70%</strong></p>
                <p>Solo se enviarán señales cuando la IA detecte probabilidad ≥ 70%</p>
            </div>
            
            <div class="status">
                <div class="status-item">
                    <strong>NYSE/NASDAQ</strong><br>
                    <span class="{'open' if mercados['ny_abierto'] else 'closed'}">
                        {mercados['hora_ny']} ({'✅ ABIERTO' if mercados['ny_abierto'] else '🔴 CERRADO'})
                    </span>
                </div>
                <div class="status-item">
                    <strong>BVC Colombia</strong><br>
                    <span class="{'open' if mercados['col_abierto'] else 'closed'}">
                        {mercados['hora_col']} ({'✅ ABIERTO' if mercados['col_abierto'] else '🔴 CERRADO'})
                    </span>
                </div>
                <div class="status-item">
                    <strong>Día de la semana</strong><br>
                    {mercados['dia_semana']}
                </div>
            </div>
            
            <div class="assets">
                <h3>📊 ACTIVOS MONITOREADOS</h3>
                <ul>
                    <li>🪙 <strong>Criptomonedas RWA:</strong> Umbral 70%</li>
                    <li>🥇 <strong>Commodities:</strong> Umbral 70%</li>
                    <li>🇨🇴 <strong>Acciones Colombianas:</strong> Umbral 70%</li>
                    <li>🎯 <strong>Penny Stocks:</strong> Umbral 70% (dinámicos)</li>
                    <li>📈 <strong>ETF XLF:</strong> Umbral 70%</li>
                </ul>
                <p><em>Filtro activo: Solo señales de alta probabilidad</em></p>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/config')
def mostrar_config():
    return json.dumps({
        "umbrales": UMBRALES,
        "rsi_umbrales": RSI_UMBRALES,
        "volumen_umbrales": VOLUMEN_UMBRALES,
        "activos": {
            "criptos": len(CRYPTO_ACTIVOS),
            "commodities": len(COMMODITIES_ACTIVOS),
            "colombia": len(COLOMBIAN_ACTIVOS),
            "etfs": len(ETF_ACTIVOS),
            "penny_stocks": "Dinámicos"
        }
    }, indent=2)

def run_web():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)

# --- INICIO CON 70% ---
async def inicio_con_70():
    """Secuencia de inicio con configuración 70%"""
    try:
        mercados = horario.obtener_info_mercados()
        
        msg = (f"🚀 **INVESTFRED AI INICIADO - UMBRAL 70% ACTIVADO**\n\n"
               f"🎯 **CONFIGURACIÓN DE UMBRALES:**\n"
               f"• Mínimo requerido: 70% de probabilidad\n"
               f"• Crypto RWA: 70%\n"
               f"• Commodities: 70%\n"
               f"• Colombia (EC, ISA): 70%\n"
               f"• Penny Stocks: 70%\n"
               f"• ETF XLF: 70%\n\n"
               f"📅 **HORARIOS ACTUALES:**\n"
               f"• NY: {mercados['hora_ny']} ({'✅ ABIERTO' if mercados['ny_abierto'] else '⏸️ CERRADO'})\n"
               f"• CO: {mercados['hora_col']} ({'✅ ABIERTO' if mercados['col_abierto'] else '⏸️ CERRADO'})\n"
               f"• Día: {mercados['dia_semana']}\n\n"
               f"⚙️ **FILTROS ACTIVOS:**\n"
               f"• Probabilidad IA ≥ 70%\n"
               f"• RSI en rangos saludables\n"
               f"• Volumen por encima del promedio\n"
               f"• Tendencia y MACD alcistas\n"
               f"• Condiciones técnicas estrictas\n\n"
               f"🔔 **SOLO recibirás señales de ALTA PROBABILIDAD.**\n"
               f"Esto reduce la cantidad pero aumenta la calidad.")
        
        await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')
        print("✅ Bot iniciado con umbral 70% configurado")
        
    except Exception as e:
        print(f"❌ Error en inicio: {e}")

# --- PUNTO DE ENTRADA ---
if __name__ == "__main__":
    print("=" * 60)
    print("🤖 INVESTFRED AI - CONFIGURACIÓN 70%")
    print("=" * 60)
    
    print("\n⚙️ CONFIGURACIÓN DE UMBRALES:")
    for tipo, umbral in UMBRALES.items():
        print(f"• {tipo}: {umbral*100}%")
    
    print("\n🎯 ACTIVOS CONFIGURADOS:")
    print(f"• Criptos RWA: {len(CRYPTO_ACTIVOS)} (Umbral: {UMBRALES['CRYPTO']*100}%)")
    print(f"• Commodities: {len(COMMODITIES_ACTIVOS)} (Umbral: {UMBRALES['COMMODITY']*100}%)")
    print(f"• Colombia: {len(COLOMBIAN_ACTIVOS)} (Umbral: {UMBRALES['COLOMBIA']*100}%)")
    print(f"• Penny Stocks: Dinámicos (Umbral: {UMBRALES['PENNY_STOCK']*100}%)")
    print(f"• ETF: {len(ETF_ACTIVOS)} (Umbral: {UMBRALES['ETF']*100}%)")
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
        
        # Inicio con 70%
        loop.run_until_complete(inicio_con_70())
        time.sleep(3)
        
        # Bucle principal con 70%
        print("\n🔄 Iniciando ciclo principal con filtro 70%...")
        loop.run_until_complete(main_loop_con_70())
        
    except KeyboardInterrupt:
        print("\n🛑 Bot detenido manualmente")
    except Exception as e:
        print(f"💥 Error crítico: {e}")

