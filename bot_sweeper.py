import os
import time
import datetime
import threading
import pytz
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import httpx
from flask import Flask

# ==============================================================================
# 1. MINI SERVIDOR HTTP PARA RENDER
# ==============================================================================
app = Flask(__name__)
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>'
@app.route('/')
def home():
    return "Bot Sweeper QUANT v3 Multi-TF activo y escuchando el mercado.", 200

def iniciar_servidor_web():
    puerto = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=puerto)

# ==============================================================================
# 2. CONFIGURACIÓN Y PARÁMETROS
# ==============================================================================
SYMBOL = "GC=F"         # Futuros del Oro (XAUUSD)
# Lista de temporalidades requeridas (formato compatible con Yahoo Finance / yfinance)
TIMEFRAMES = ["3m", "5m", "15m", "30m", "1h", "4h", "1d", "1wk", "1mo"]

TF1 = "1h"
TF2 = "4h"

LEN_PIVOTE = 3
CLV_TRIG_MIN = 0.35
MODO_BARRIDO = True
MODO_BOS = True

EMA_LEN = 50
EXIGIR_MACRO = True

USAR_SESION = True
SESS_LONDRES_START, SESS_LONDRES_END = 7, 13
SESS_NY_START, SESS_NY_END = 13, 21

TF_VOL = "1h"
VOL_LEN = 20
MULT_VOL = 1.15
CLV_MIN = 0.3

# Variables de entorno para Telegram
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "TU_TELEGRAM_BOT_TOKEN_AQUI")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "TU_TELEGRAM_CHAT_ID_AQUI")

def enviar_telegram(mensaje: str):
    if TELEGRAM_TOKEN == "TU_TELEGRAM_BOT_TOKEN_AQUI":
        print(f"\n[SIMULACIÓN TELEGRAM]:\n{mensaje}\n")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "Markdown"
    }
    try:
        httpx.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error al enviar a Telegram: {e}")

def calcular_clv(df: pd.DataFrame) -> pd.Series:
    rng = (df['High'] - df['Low']).replace(0, 0.00001)
    return ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / rng

def esta_en_sesion(dt: datetime.datetime) -> bool:
    if not USAR_SESION:
        return True
    hora_utc = dt.astimezone(pytz.utc).hour
    return (SESS_LONDRES_START <= hora_utc < SESS_LONDRES_END) or (SESS_NY_START <= hora_utc < SESS_NY_END)

def obtener_pivotes(df: pd.DataFrame, left: int, right: int):
    highs, lows, n = df['High'].values, df['Low'].values, len(df)
    swing_highs, swing_lows = [None] * n, [None] * n
    
    for i in range(left, n - right):
        window_h = highs[i - left : i + right + 1]
        if max(window_h) == highs[i] and list(window_h).count(highs[i]) == 1:
            swing_highs[i + right] = highs[i]
            
        window_l = lows[i - left : i + right + 1]
        if min(window_l) == lows[i] and list(window_l).count(lows[i]) == 1:
            swing_lows[i + right] = lows[i]
            
    return pd.Series(swing_highs, index=df.index).ffill(), pd.Series(swing_lows, index=df.index).ffill()

# ==============================================================================
# 3. EVALUACIÓN POR TEMPORALIDAD
# ==============================================================================
def evaluar_tf(tf: str):
    # Determinar el periodo necesario de descarga según el timeframe
    periodo = "5d" if tf in ["3m", "5m", "15m", "30m"] else "60d" if tf in ["1h", "4h"] else "2y"
    
    df = yf.download(SYMBOL, period=periodo, interval=tf, progress=False)
    df_tf1 = yf.download(SYMBOL, period="60d", interval=TF1, progress=False)
    df_tf2 = yf.download(SYMBOL, period="120d", interval=TF2, progress=False)
    
    if df.empty or df_tf1.empty or df_tf2.empty:
        return

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        df_tf1.columns = df_tf1.columns.get_level_values(0)
        df_tf2.columns = df_tf2.columns.get_level_values(0)

    # Filtro Macro (TF1 / TF2)
    df_tf1['EMA'] = ta.ema(df_tf1['Close'], length=EMA_LEN)
    df_tf2['EMA'] = ta.ema(df_tf2['Close'], length=EMA_LEN)
    
    tend_tf1 = df_tf1['Close'].iloc[-1] > df_tf1['EMA'].iloc[-1]
    tend_tf2 = df_tf2['Close'].iloc[-1] > df_tf2['EMA'].iloc[-1]
    
    tend_alc = tend_tf1 and (tend_tf2 if EXIGIR_MACRO else True)
    tend_baj = (not tend_tf1) and ((not tend_tf2) if EXIGIR_MACRO else True)
    grado_a = tend_tf1 == tend_tf2

    # Veto por Volumen HTF
    df_vol = yf.download(SYMBOL, period="30d", interval=TF_VOL, progress=False)
    if isinstance(df_vol.columns, pd.MultiIndex):
        df_vol.columns = df_vol.columns.get_level_values(0)
        
    df_vol['VolMA'] = ta.sma(df_vol['Volume'], length=VOL_LEN)
    df_vol['CLV'] = calcular_clv(df_vol)
    
    vol_htf, vol_ma, clv_htf = df_vol['Volume'].iloc[-1], df_vol['VolMA'].iloc[-1], df_vol['CLV'].iloc[-1]
    veto_long = (vol_htf > vol_ma * MULT_VOL) and (clv_htf < -CLV_MIN)
    veto_short = (vol_htf > vol_ma * MULT_VOL) and (clv_htf > CLV_MIN)

    # Cálculo en TF Específico
    df['CLV'] = calcular_clv(df)
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    df['SwingHigh'], df['SwingLow'] = obtener_pivotes(df, LEN_PIVOTE, LEN_PIVOTE)

    if len(df) < 4:
        return

    c_vela, p_vela = df.iloc[-2], df.iloc[-3]
    en_sesion = esta_en_sesion(df.index[-2]) if tf in ["3m", "5m", "15m", "30m", "1h"] else True
    
    clv_trig = c_vela['CLV']
    disp_alc, disp_baj = clv_trig >= CLV_TRIG_MIN, clv_trig <= -CLV_TRIG_MIN

    swing_low, swing_high = c_vela['SwingLow'], c_vela['SwingHigh']
    sweep_low = pd.notna(swing_low) and (c_vela['Low'] < swing_low) and (c_vela['Close'] > swing_low)
    sweep_high = pd.notna(swing_high) and (c_vela['High'] > swing_high) and (c_vela['Close'] < swing_high)
    bos_up = pd.notna(swing_high) and (c_vela['Close'] > swing_high) and (p_vela['Close'] <= swing_high)
    bos_dn = pd.notna(swing_low) and (c_vela['Close'] < swing_low) and (p_vela['Close'] >= swing_low)

    sig_long = en_sesion and (not veto_long) and tend_alc and disp_alc and ((MODO_BARRIDO and sweep_low) or (MODO_BOS and bos_up))
    sig_short = en_sesion and (not veto_short) and tend_baj and disp_baj and ((MODO_BARRIDO and sweep_high) or (MODO_BOS and bos_dn))

    # Formatear TF para el mensaje
    tf_label = tf.upper().replace("WK", "W").replace("MO", "M")

    if sig_long:
        tipo = "BARRIDO LONG" if (MODO_BARRIDO and sweep_low) else "🚀 CONTINUACIÓN LONG"
        grado = "(A+)" if grado_a else "(B)"
        me = max(swing_high - swing_low if pd.notna(swing_high) and pd.notna(swing_low) else 4.0 * c_vela['ATR'], 2.0 * c_vela['ATR'])
        msg = (
            f"🔥 *SEÑAL {tipo} {grado}*\n"
            f"⏱️ *Timeframe:* `{tf_label}`\n"
            f"📈 *Activo:* {SYMBOL}\n"
            f"💲 *Precio Entrada:* `{c_vela['Close']:.2f}`\n"
            f"🎯 *Parcial TP1 (15%):* `{c_vela['Close'] + (me * 0.15):.2f}`\n"
            f"🎯 *Parcial TP2 (20%):* `{c_vela['Close'] + (me * 0.20):.2f}`\n"
            f"🛡️ *Inval. Estructural:* `{swing_low:.2f}`"
        )
        enviar_telegram(msg)

    elif sig_short:
        tipo = "🎯 BARRIDO SHORT" if (MODO_BARRIDO and sweep_high) else "🚀 CONTINUACIÓN SHORT"
        grado = "(A+)" if grado_a else "(B)"
        me = max(swing_high - swing_low if pd.notna(swing_high) and pd.notna(swing_low) else 4.0 * c_vela['ATR'], 2.0 * c_vela['ATR'])
        msg = (
            f"🚨 *SEÑAL {tipo} {grado}*\n"
            f"⏱️ *Timeframe:* `{tf_label}`\n"
            f"📉 *Activo:* {SYMBOL}\n"
            f"💲 *Precio Entrada:* `{c_vela['Close']:.2f}`\n"
            f"🎯 *Parcial TP1 (15%):* `{c_vela['Close'] - (me * 0.15):.2f}`\n"
            f"🎯 *Parcial TP2 (20%):* `{c_vela['Close'] - (me * 0.20):.2f}`\n"
            f"🛡️ *Inval. Estructural:* `{swing_high:.2f}`"
        )
        enviar_telegram(msg)

def analizar_mercado():
    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Escaneando {SYMBOL} en múltiples Timeframes...")
    for tf in TIMEFRAMES:
        try:
            evaluar_tf(tf)
        except Exception as e:
            print(f"Error evaluando TF {tf}: {e}")

# ==============================================================================
# 4. BUCLE PRINCIPAL
# ==============================================================================
if __name__ == "__main__":
    t = threading.Thread(target=iniciar_servidor_web, daemon=True)
    t.start()

    while True:
        try:
            analizar_mercado()
        except Exception as e:
            print(f"Error en bucle principal: {e}")
        
        # Escanea todas las temporalidades cada 3 minutos
        time.sleep(180)
