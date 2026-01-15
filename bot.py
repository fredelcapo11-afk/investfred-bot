import yfinance as yf
import pandas_ta as ta
import asyncio
import pandas as pd
import os
import requests
import matplotlib.pyplot as plt
import io
from telegram import Bot
from datetime import datetime, timedelta
from sklearn.ensemble import RandomForestClassifier
import warnings

warnings.filterwarnings("ignore")

# ==========================================
# CONFIGURACIÓN
# ==========================================
TOKEN = "8575636448:AAH7VP5H6xHiQbuoGh1vn1xrpYbSAZbrgxQ"
CHAT_ID = "5239530286"
FMP_API_KEY = "XyB0qniOLoNc0nEtMj90a2ETRsT9Z8Js"

bot = Bot(token=TOKEN)

def detectar_zonas(df):
    soporte = df['Low'].rolling(window=20).min().iloc[-1]
    resistencia = df['High'].rolling(window=20).max().iloc[-1]
    return soporte, resistencia

async def enviar_grafico(ticker, df):
    try:
        # Cálculos de Indicadores
        bbands = ta.bbands(df['Close'], length=20, std=2)
        rsi = ta.rsi(df['Close'], length=14)
        macd = ta.macd(df['Close'])
        stoch = ta.stoch(df['High'], df['Low'], df['Close'])
        soporte, resistencia = detectar_zonas(df)
        
        df = pd.concat([df, bbands, rsi, macd, stoch], axis=1)
        df_plot = df.tail(45)
        
        plt.style.use('dark_background')
        # 4 paneles: Precio, RSI, MACD, Estocástico
        fig, (ax1, ax2, ax3, ax4) = plt.subplots(4, 1, figsize=(14, 15), 
                                                 gridspec_kw={'height_ratios': [3, 1, 1, 1]})
        
        # --- PANEL 1: PRECIO + VOLUMEN ---
        ax1.plot(df_plot.index, df_plot['Close'], label='Precio', color='#00ff00', linewidth=2)
        ax1_vol = ax1.twinx()
        colores_vol = ['#26a69a' if df_plot['Close'].iloc[i] >= df_plot['Open'].iloc[i] else '#ef5350' for i in range(len(df_plot))]
        ax1_vol.bar(df_plot.index, df_plot['Volume'], alpha=0.15, color=colores_vol)
        ax1_vol.axis('off')
        ax1.axhline(resistencia, color='#ff5252', linestyle='--', alpha=0.4, label='Oferta')
        ax1.axhline(soporte, color='#2196f3', linestyle='--', alpha=0.4, label='Demanda')
        ax1.set_title(f"Análisis PRO: {ticker}", fontsize=16)
        ax1.legend(loc='upper left')

        # --- PANEL 2: RSI ---
        ax2.plot(df_plot.index, df_plot.filter(like='RSI_14'), color='#ffa726')
        ax2.axhline(70, color='red', alpha=0.2); ax2.axhline(30, color='green', alpha=0.2)
        ax2.set_ylabel('RSI')

        # --- PANEL 3: MACD ---
        ax3.plot(df_plot.index, df_plot.filter(like='MACD_12_26_9'), label='MACD', color='#29b6f6')
        ax3.plot(df_plot.index, df_plot.filter(like='MACDs_12_26_9'), label='Señal', color='#ff7043')
        ax3.bar(df_plot.index, df_plot.filter(like='MACDh_12_26_9'), alpha=0.2, color='white')
        ax3.set_ylabel('MACD')

        # --- PANEL 4: ESTOCÁSTICO ---
        ax4.plot(df_plot.index, df_plot.filter(like='STOCHk_14_3_3'), label='%K', color='#e91e63')
        ax4.plot(df_plot.index, df_plot.filter(like='STOCHd_14_3_3'), label='%D', color='#9c27b0')
        ax4.axhline(80, color='red', linestyle=':', alpha=0.3)
        ax4.axhline(20, color='green', linestyle=':', alpha=0.3)
        ax4.set_ylabel('Stoch')
        ax4.legend(loc='upper left')

        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=100)
        buf.seek(0)
        plt.close(fig) # Liberar memoria
        
        await bot.send_photo(chat_id=CHAT_ID, photo=buf)
    except Exception as e:
        print(f"Error gráfico: {e}")

def predecir_tendencia(df, ticker):
    try:
        data = df.copy()
        data['RSI'] = ta.rsi(data['Close'], length=14)
        vol_promedio = data['Volume'].rolling(20).mean()
        data['Vol_Rel'] = data['Volume'] / vol_promedio
        data['Target'] = (data['Close'].shift(-1) > data['Close']).astype(int)
        data = data.dropna()
        X = data[['RSI', 'Vol_Rel']]
        y = data['Target']
        model = RandomForestClassifier(n_estimators=50, random_state=42)
        model.fit(X[:-1], y[:-1])
        prob = model.predict_proba(X.tail(1))[0][1]
        return prob, data['RSI'].iloc[-1]
    except: return 0, 50

async def main():
    print("🚀 INVESTFRED v16.8: Análisis con Estocástico Activo...")
    while True:
        try:
            url = f"https://financialmodelingprep.com/api/v3/stock-screener?priceLowerThan=5&volumeMoreThan=1000000&exchange=NASDAQ,NYSE&limit=25&apikey={FMP_API_KEY}"
            data_fmp = requests.get(url).json()
            activos = [(i['symbol'], i.get('sector', 'Penny')) for i in data_fmp] if isinstance(data_fmp, list) else [("SNDL", "Respaldo"), ("NIO", "Respaldo")]
            globales = [("^IXIC", "NASDAQ"), ("BTC-USD", "Cripto"), ("GC=F", "Oro")]

            for t, s in activos + globales:
                df = yf.download(t, period="6mo", interval="1d", progress=False)
                if df is None or df.empty: continue
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                
                prob, rsi_val = predecir_tendencia(df, t)
                if prob > 0.70:
                    precio = float(df['Close'].iloc[-1])
                    msg = f"💎 **SEÑAL DETECTADA**\n\nActivo: `{t}`\nPrecio: ${precio:.2f}\nRSI: {rsi_val:.1f}\nConfianza: {prob:.1%}"
                    await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')
                    await enviar_grafico(t, df)
                await asyncio.sleep(2)
            await asyncio.sleep(3600)
        except Exception as e:
            print(f"❌ Error: {e}")
            await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
