import yfinance as yf
import pandas_ta as ta
import asyncio
import pandas as pd
import os
import logging
import json
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from datetime import datetime
from finvizfinance.screener.overview import Overview
from sklearn.ensemble import RandomForestClassifier
import warnings

warnings.filterwarnings("ignore")

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==========================================
# CONFIGURACIÓN
# ==========================================
TOKEN = os.environ.get("TELEGRAM_TOKEN", "8575636448:AAH7VP5H6xHiQbuoGh1vn1xrpYbSAZbrgxQ")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "5239530286")
ARCHIVO_LOG = "registro_ml_sectores.csv"
ARCHIVO_USUARIOS = "usuarios_autorizados.json"

# Almacenar usuarios autorizados
def cargar_usuarios():
    if os.path.exists(ARCHIVO_USUARIOS):
        with open(ARCHIVO_USUARIOS, 'r') as f:
            return json.load(f)
    return {CHAT_ID: "admin"}

def guardar_usuarios(usuarios):
    with open(ARCHIVO_USUARIOS, 'w') as f:
        json.dump(usuarios, f)

# --- FUNCIONES DE ANÁLISIS ---
def registrar_prediccion(ticker, sector, precio, prob):
    df_new = pd.DataFrame([[datetime.now(), ticker, sector, precio, prob]], 
                          columns=['Fecha', 'Ticker', 'Sector', 'Precio_Entrada', 'Probabilidad'])
    if not os.path.exists(ARCHIVO_LOG):
        df_new.to_csv(ARCHIVO_LOG, index=False)
    else:
        df_new.to_csv(ARCHIVO_LOG, mode='a', header=False, index=False)

async def auditar_por_sector(context: ContextTypes.DEFAULT_TYPE, chat_id: str):
    if not os.path.exists(ARCHIVO_LOG): 
        await context.bot.send_message(chat_id=chat_id, text="📊 No hay datos históricos para auditar")
        return
    
    await context.bot.send_message(chat_id=chat_id, text="📊 Calculando Win Rate por sector...")
    df = pd.read_csv(ARCHIVO_LOG)
    resumen_sectores = {}

    for i, row in df.iterrows():
        try:
            sector = row['Sector']
            if sector not in resumen_sectores:
                resumen_sectores[sector] = {'aciertos': 0, 'total': 0}
            
            data = yf.download(row['Ticker'], period="5d", interval="1d", progress=False)
            if isinstance(data.columns, pd.MultiIndex): 
                data.columns = data.columns.get_level_values(0)
            
            precio_actual = float(data['Close'].iloc[-1])
            resumen_sectores[sector]['total'] += 1
            if precio_actual > row['Precio_Entrada']:
                resumen_sectores[sector]['aciertos'] += 1
        except Exception as e:
            logger.error(f"Error procesando {row['Ticker']}: {e}")
            continue
    
    if resumen_sectores:
        reporte = "📊 *ESTADÍSTICAS POR SECTOR* 📊\n\n"
        for sec, stats in resumen_sectores.items():
            wr = (stats['aciertos'] / stats['total']) * 100 if stats['total'] > 0 else 0
            reporte += f"• *{sec}*: {wr:.1f}% Win Rate ({stats['total']} ops)\n"
        await context.bot.send_message(chat_id=chat_id, text=reporte, parse_mode='Markdown')
    else:
        await context.bot.send_message(chat_id=chat_id, text="❌ No se pudieron calcular estadísticas")

def predecir_tendencia(df):
    try:
        data = df.copy()
        data['Target'] = (data['Close'].shift(-1) > data['Close']).astype(int)
        data['RSI'] = ta.rsi(data['Close'], length=14)
        data['Vol_Rel'] = data['Volume'] / data['Volume'].rolling(20).mean()
        data = data.dropna()
        X = data[['RSI', 'Vol_Rel']]
        y = data['Target']
        model = RandomForestClassifier(n_estimators=50, random_state=42)
        model.fit(X[:-1], y[:-1])
        return model.predict_proba(X.tail(1))[0][1]
    except Exception as e:
        logger.error(f"Error en predicción: {e}")
        return 0.5

async def analizar_activo(ticker, sector, context: ContextTypes.DEFAULT_TYPE, chat_id: str):
    try:
        await context.bot.send_message(chat_id=chat_id, text=f"📈 Analizando {ticker}...")
        
        df = yf.download(ticker, period="1y", interval="1d", progress=False)
        if df is None or df.empty: 
            await context.bot.send_message(chat_id=chat_id, text=f"❌ No se pudo obtener datos de {ticker}")
            return
        
        if isinstance(df.columns, pd.MultiIndex): 
            df.columns = df.columns.get_level_values(0)
        
        df = df.apply(pd.to_numeric, errors='coerce').dropna()
        
        if len(df) < 50:
            await context.bot.send_message(chat_id=chat_id, text=f"❌ Datos insuficientes para {ticker}")
            return
            
        prob = predecir_tendencia(df)
        precio = float(df['Close'].iloc[-1])
        
        if prob > 0.68:
            registrar_prediccion(ticker, sector, precio, prob)
            msg = (f"🧠 *SEÑAL DETECTADA*\n"
                   f"• Activo: `{ticker}`\n"
                   f"• Sector: {sector}\n"
                   f"• Precio: ${precio:.2f}\n"
                   f"• Prob. éxito: {prob:.1%}")
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
        else:
            await context.bot.send_message(
                chat_id=chat_id, 
                text=f"ℹ️ {ticker}: Probabilidad {prob:.1%} (umbral: 68%)"
            )
            
    except Exception as e:
        logger.error(f"Error analizando {ticker}: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Error analizando {ticker}")

# ==========================================
# COMANDOS DE TELEGRAM
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mensaje de bienvenida"""
    user_id = str(update.effective_user.id)
    usuarios = cargar_usuarios()
    
    if user_id in usuarios:
        welcome_text = (
            "🤖 *INVESTFRED AI - Listo*\n\n"
            "Comandos disponibles:\n"
            "• /start - Ver este mensaje\n"
            "• /analizar - Ejecutar análisis completo\n"
            "• /auditar - Ver estadísticas por sector\n"
            "• /analizar_ticker TICKER - Analizar un activo específico\n"
            "• /pennys - Buscar penny stocks prometedores\n"
            "• /globales - Analizar activos globales\n"
            "• /autorizar ID - Autorizar nuevo usuario\n"
            "• /ayuda - Ver ayuda completa\n"
        )
    else:
        welcome_text = "❌ No estás autorizado para usar este bot."
    
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def analizar_completo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ejecutar análisis completo"""
    user_id = str(update.effective_user.id)
    usuarios = cargar_usuarios()
    
    if user_id not in usuarios:
        await update.message.reply_text("❌ No estás autorizado para usar este bot.")
        return
    
    chat_id = update.effective_chat.id
    await update.message.reply_text("⚙️ *Iniciando análisis completo...*", parse_mode='Markdown')
    
    # Auditoría primero
    await auditar_por_sector(context, chat_id)
    await asyncio.sleep(1)
    
    # Buscar penny stocks
    try:
        await update.message.reply_text("🔍 Buscando penny stocks...")
        f = Overview()
        f.set_filter(filters_dict={'Price': 'Under $5', 'Relative Volume': 'Over 2.0'})
        pennys = f.screener_view()[['Ticker', 'Sector']].head(8).values.tolist()
    except Exception as e:
        logger.error(f"Error obteniendo pennys: {e}")
        pennys = []
        await update.message.reply_text("⚠️ No se pudieron obtener penny stocks")
    
    # Analizar pennys
    if pennys:
        await update.message.reply_text(f"📊 Analizando {len(pennys)} penny stocks...")
        for t, s in pennys:
            await analizar_activo(t, s, context, chat_id)
            await asyncio.sleep(1.5)
    
    # Analizar activos globales
    globales = [("BTC-USD", "Cripto"), ("ETH-USD", "Cripto"), ("GC=F", "Oro"), ("CL=F", "Energía")]
    await update.message.reply_text("🌍 Analizando activos globales...")
    
    for t, s in globales:
        await analizar_activo(t, s, context, chat_id)
        await asyncio.sleep(1.5)
    
    await update.message.reply_text("✅ *Análisis completado*", parse_mode='Markdown')

async def analizar_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analizar un ticker específico"""
    user_id = str(update.effective_user.id)
    usuarios = cargar_usuarios()
    
    if user_id not in usuarios:
        await update.message.reply_text("❌ No estás autorizado.")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Uso: /analizar_ticker TICKER\nEj: /analizar_ticker AAPL")
        return
    
    ticker = context.args[0].upper()
    sector = "Personalizado"
    
    await analizar_activo(ticker, sector, context, update.effective_chat.id)

async def auditar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar estadísticas por sector"""
    user_id = str(update.effective_user.id)
    usuarios = cargar_usuarios()
    
    if user_id not in usuarios:
        await update.message.reply_text("❌ No estás autorizado.")
        return
    
    await auditar_por_sector(context, update.effective_chat.id)

async def buscar_pennys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buscar penny stocks prometedores"""
    user_id = str(update.effective_user.id)
    usuarios = cargar_usuarios()
    
    if user_id not in usuarios:
        await update.message.reply_text("❌ No estás autorizado.")
        return
    
    chat_id = update.effective_chat.id
    await update.message.reply_text("🔍 Buscando penny stocks (<$5, Vol Rel > 2)...")
    
    try:
        f = Overview()
        f.set_filter(filters_dict={'Price': 'Under $5', 'Relative Volume': 'Over 2.0'})
        df = f.screener_view()
        
        if not df.empty:
            pennys = df[['Ticker', 'Sector', 'Price']].head(10).values.tolist()
            respuesta = "📊 *Penny Stocks Detectados:*\n\n"
            
            for t, s, p in pennys:
                respuesta += f"• `{t}` - {s} (${p})\n"
            
            respuesta += "\nUsa /analizar_ticker TICKER para analizar uno específico."
            await context.bot.send_message(chat_id=chat_id, text=respuesta, parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ No se encontraron penny stocks con los filtros aplicados.")
            
    except Exception as e:
        logger.error(f"Error buscando pennys: {e}")
        await update.message.reply_text("❌ Error al buscar penny stocks.")

async def analizar_globales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analizar activos globales"""
    user_id = str(update.effective_user.id)
    usuarios = cargar_usuarios()
    
    if user_id not in usuarios:
        await update.message.reply_text("❌ No estás autorizado.")
        return
    
    chat_id = update.effective_chat.id
    globales = [
        ("BTC-USD", "Cripto"),
        ("ETH-USD", "Cripto"), 
        ("GC=F", "Oro"),
        ("CL=F", "Energía"),
        ("SI=F", "Plata"),
        ("EURUSD=X", "Forex"),
        ("^GSPC", "Indice (S&P500)"),
        ("^IXIC", "Indice (Nasdaq)")
    ]
    
    await update.message.reply_text("🌍 Analizando activos globales...")
    
    for t, s in globales:
        await analizar_activo(t, s, context, chat_id)
        await asyncio.sleep(1.5)
    
    await update.message.reply_text("✅ Análisis global completado")

async def autorizar_usuario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Autorizar a un nuevo usuario (solo admin)"""
    user_id = str(update.effective_user.id)
    usuarios = cargar_usuarios()
    
    # Solo el admin puede autorizar
    if user_id != CHAT_ID:
        await update.message.reply_text("❌ Solo el administrador puede autorizar usuarios.")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Uso: /autorizar ID_USUARIO\n(Ej: /autorizar 123456789)")
        return
    
    nuevo_id = context.args[0]
    usuarios[nuevo_id] = "autorizado"
    guardar_usuarios(usuarios)
    
    await update.message.reply_text(f"✅ Usuario {nuevo_id} autorizado.")

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar ayuda"""
    ayuda_text = (
        "🤖 *INVESTFRED AI - Comandos*\n\n"
        "• /start - Iniciar bot\n"
        "• /analizar - Análisis completo (auditoría + pennys + globales)\n"
        "• /auditar - Estadísticas de rendimiento por sector\n"
        "• /analizar_ticker TICKER - Analizar activo específico\n"
        "• /pennys - Buscar penny stocks prometedores\n"
        "• /globales - Analizar activos globales\n"
        "• /autorizar ID - Autorizar usuario (solo admin)\n"
        "• /ayuda - Ver esta ayuda\n\n"
        "*Ejemplos:*\n"
        "`/analizar_ticker AAPL`\n"
        "`/analizar_ticker TSLA`\n"
        "`/analizar_ticker BTC-USD`"
    )
    await update.message.reply_text(ayuda_text, parse_mode='Markdown')

# ==========================================
# FUNCIÓN PRINCIPAL
# ==========================================

def main():
    """Iniciar el bot"""
    # Crear aplicación
    application = Application.builder().token(TOKEN).build()
    
    # Registrar manejadores de comandos
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("analizar", analizar_completo))
    application.add_handler(CommandHandler("auditar", auditar))
    application.add_handler(CommandHandler("analizar_ticker", analizar_ticker))
    application.add_handler(CommandHandler("pennys", buscar_pennys))
    application.add_handler(CommandHandler("globales", analizar_globales))
    application.add_handler(CommandHandler("autorizar", autorizar_usuario))
    application.add_handler(CommandHandler("ayuda", ayuda))
    application.add_handler(CommandHandler("help", ayuda))
    
    # Manejar mensajes no reconocidos
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ayuda))
    
    # Iniciar el bot
    print("🤖 INVESTFRED AI iniciado. Presiona Ctrl+C para detener.")
    print("📱 Ahora puedes usar comandos desde Telegram:")
    print("   • Envía /start al bot")
    print("   • Luego usa /analizar para ejecutar el análisis")
    
    # Ejecutar en modo polling (escucha continuamente)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
