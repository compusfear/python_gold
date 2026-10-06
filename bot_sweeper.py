import os
import datetime
import pytz
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import httpx
from flask import Flask, request, jsonify

# ==============================================================================
# 1. CONFIGURACIÓN Y SERVIDOR FLASK
# ==============================================================================
app = Flask(__name__)

SYMBOL = "GC=F"         # Futuros del Oro (XAUUSD)
TF1 = "1h"
TF2 = "4h"
EMA_LEN = 50
EXIGIR_MACRO = True

USAR_SESION = True
SESS_LONDRES_START, SESS_LONDRES_END = 7, 13
SESS_NY_START, SESS_NY_END = 13, 21

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "TU_TELEGRAM_BOT_TOKEN_AQUI")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "TU_TELEGRAM_CHAT_ID_AQUI")

# ==============================================================================
# 2. FUNCIONES AUXILIARES Y NOTIFICACIONES
# ==============================================================================
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

def esta_en_sesion(dt: datetime.datetime) -> bool:
    if not USAR_SESION:
        return True
    hora_utc = dt.astimezone(pytz.utc).hour
    return (SESS_LONDRES_START <= hora_utc < SESS_LONDRES_END) or (SESS_NY_START <= hora_utc < SESS_NY_END)

def validar_filtro_macro():
    """Descarga datos HTF rápidamente para comprobar alineación con la EMA 50."""
    try:
        df_tf1 = yf.download(SYMBOL, period="30d", interval=TF1, progress=False)
        df_tf2 = yf.download(SYMBOL, period="60d", interval=TF2, progress=False)

        if df_tf1.empty or df_tf2.empty:
            return True, True, True

        if isinstance(df_tf1.columns, pd.MultiIndex):
            df_tf1.columns = df_tf1.columns.get_level_values(0)
            df_tf2.columns = df_tf2.columns.get_level_values(0)

        df_tf1['EMA'] = ta.ema(df_tf1['Close'], length=EMA_LEN)
        df_tf2['EMA'] = ta.ema(df_tf2['Close'], length=EMA_LEN)

        tend_tf1 = df_tf1['Close'].iloc[-1] > df_tf1['EMA'].iloc[-1]
        tend_tf2 = df_tf2['Close'].iloc[-1] > df_tf2['EMA'].iloc[-1]

        tend_alc = tend_tf1 and (tend_tf2 if EXIGIR_MACRO else True)
        tend_baj = (not tend_tf1) and ((not tend_tf2) if EXIGIR_MACRO else True)
        grado_a = tend_tf1 == tend_tf2

        return tend_alc, tend_baj, grado_a
    except Exception as e:
        print(f"Error verificando filtro macro: {e}")
        return True, True, False

# ==============================================================================
# 3. ENDPOINTS HTTP Y PROCESAMIENTO WEBHOOK
# ==============================================================================
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    return "Bot Sweeper QUANT v3 (Webhook Engine) activo y escuchando.", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"status": "error", "message": "Payload JSON inválido o vacío"}), 400

        # Extraer campos de la alerta de TradingView
        ticker = data.get("ticker", SYMBOL)
        timeframe = data.get("timeframe", "3M")
        direccion = data.get("action", "").upper()  # "BUY" o "SELL"
        tipo_senal = data.get("type", "BARRIDO")    # "BARRIDO" o "BOS"
        precio = float(data.get("price", 0))
        swing_level = float(data.get("invalidation", 0))

        ahora_utc = datetime.datetime.now(pytz.utc)

        # 1. Validar filtro de sesión
        if not esta_en_sesion(ahora_utc):
            print(f"[{ahora_utc}] Señal ignorada: Fuera de horario de sesión (Londres/NY).")
            return jsonify({"status": "ignored", "reason": "Fuera de sesion"}), 200

        # 2. Validar tendencia Macro (HTF)
        tend_alc, tend_baj, grado_a = validar_filtro_macro()

        if direccion == "BUY" and not tend_alc:
            print(f"[{ahora_utc}] Señal LONG rechazada por filtro macro HTF.")
            return jsonify({"status": "ignored", "reason": "Macro tendencia bajista"}), 200

        if direccion == "SELL" and not tend_baj:
            print(f"[{ahora_utc}] Señal SHORT rechazada por filtro macro HTF.")
            return jsonify({"status": "ignored", "reason": "Macro tendencia alcista"}), 200

        # 3. Calcular targets de parciales
        rango_est = abs(precio - swing_level) if swing_level > 0 else 4.0
        grado_str = "(A+)" if grado_a else "(B)"

        if direccion == "BUY":
            tp1 = precio + (rango_est * 0.15)
            tp2 = precio + (rango_est * 0.20)
            msg = (
                f"🔥 *SEÑAL {tipo_senal} LONG {grado_str}*\n"
                f"⏱️ *Timeframe:* `{timeframe}`\n"
                f"📈 *Activo:* {ticker}\n"
                f"💲 *Precio Entrada:* `{precio:.2f}`\n"
                f"🎯 *Parcial TP1 (15%):* `{tp1:.2f}`\n"
                f"🎯 *Parcial TP2 (20%):* `{tp2:.2f}`\n"
                f"🛡️ *Inval. Estructural:* `{swing_level:.2f}`"
            )
        else:
            tp1 = precio - (rango_est * 0.15)
            tp2 = precio - (rango_est * 0.20)
            msg = (
                f"🚨 *SEÑAL {tipo_senal} SHORT {grado_str}*\n"
                f"⏱️ *Timeframe:* `{timeframe}`\n"
                f"📉 *Activo:* {ticker}\n"
                f"💲 *Precio Entrada:* `{precio:.2f}`\n"
                f"🎯 *Parcial TP1 (15%):* `{tp1:.2f}`\n"
                f"🎯 *Parcial TP2 (20%):* `{tp2:.2f}`\n"
                f"🛡️ *Inval. Estructural:* `{swing_level:.2f}`"
            )

        enviar_telegram(msg)
        return jsonify({"status": "success", "message": "Alerta procesada y enviada"}), 200

    except Exception as e:
        print(f"Error procesando webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ==============================================================================
# 4. ARRANQUE DEL SERVIDOR
# ==============================================================================
if __name__ == "__main__":
    puerto = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=puerto)
