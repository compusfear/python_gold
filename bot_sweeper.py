//@version=6
indicator("Sweeper QUANT v3 — Entrada Exacta + Gestión 15/20 + Runner", shorttitle="SQv3", overlay=true, max_labels_count=500, max_lines_count=500)

// ════════════════════════════════════════════════════════════════
//  BASADO EN EVIDENCIA: Fxnx (1000 trades), Oukhouya 2026 (XAUUSD H1,
//  Sharpe 1.18), Mahadzva 2026 (SSRN), Medium CLV (AAPL 00-24).
//  Regla de oro: la señal se imprime en la VELA GATILLO confirmada.
// ════════════════════════════════════════════════════════════════

// ── Entradas: Estructura ──
grpS = "1) Estructura y Gatillo"
lenPivote   = input.int(3, "Confirmación de pivotes (menor = señal más temprana)", minval=1, group=grpS)
clvTrigMin  = input.float(0.35, "Fuerza de vela gatillo (CLV mínimo)", minval=0.1, maxval=1.0, step=0.05, group=grpS, tooltip="CLV=((C-L)-(H-C))/(H-L). 0.35 = cierre en el ~67% superior/inferior del rango: vela de desplazamiento.")
cooldown    = input.int(3, "Velas mínimas entre señales", minval=0, group=grpS)
modoBarrido = input.bool(true,  "Señales por BARRIDO (rechazo de liquidez)", group=grpS)
modoBOS     = input.bool(true,  "Señales por CONTINUACIÓN (BOS con desplazamiento)", group=grpS, tooltip="Caza impulsos de tendencia fuerte sin retroceso: lo que tu indicador anterior no marcaba.")

// ── Entradas: Multi-Timeframe ──
grpT = "2) Tendencia Multi-TF"
tf1 = input.timeframe("60",  "TF tendencia principal", group=grpT)
tf2 = input.timeframe("240", "TF tendencia macro", group=grpT)
emaLen = input.int(50, "EMA de tendencia", minval=10, group=grpT)
exigirMacro = input.bool(true, "Exigir alineación macro (señal A+)", group=grpT, tooltip="Si está activo, solo opera cuando TF1 y TF2 coinciden. Desactívalo para más señales (grado B).")

// ── Entradas: Sesión y Volumen ──
grpV = "3) Sesión y Volumen Institucional"
usarSesion = input.bool(true, "Filtrar por sesión Londres/NY", group=grpV)
sessLondres = input.session("0700-1300", "Sesión Londres (UTC)", group=grpV)
sessNY      = input.session("1300-2100", "Sesión Nueva York (UTC)", group=grpV)
tfVol   = input.timeframe("60", "TF de volumen", group=grpV)
volLen  = input.int(20, "Media de volumen HTF", minval=5, group=grpV)
multVol = input.float(1.15, "Umbral volumen significativo", minval=1.0, step=0.05, group=grpV)
clvMin  = input.float(0.3, "CLV HTF para veto", minval=0.1, maxval=1.0, step=0.1, group=grpV)

// ── Entradas: Gestión sin SL/TP (tu método) ──
grpG = "4) Gestión: parcial 15/20 + a salvo + runner"
metodoME = input.string("Rango de estructura", "Movimiento Esperado (ME)", options=["Rango de estructura", "ATR xN"], group=grpG)
atrME    = input.float(4.0, "Multiplo ATR si ME=ATR xN", minval=1.0, step=0.5, group=grpG)
pctTP1   = input.float(15.0, "Parcial 1 (% del ME)", minval=5, step=5, group=grpG)
pctTP2   = input.float(20.0, "Parcial 2 (% del ME)", minval=5, step=5, group=grpG)
beBufATR = input.float(0.10, "Colchón ATR para 'a salvo'", minval=0.0, step=0.05, group=grpG, tooltip="Tras tocar TP1, nivel de puesta a salvo = entrada + colchón (cubre spread/comisión).")
modoTrail = input.string("Estructura (pivotes)", "Salida del runner", options=["Estructura (pivotes)", "Chandelier ATR"], group=grpG)
atrTrail  = input.float(3.0, "ATR del chandelier", minval=1.0, step=0.5, group=grpG)

// ════════════════ NÚCLEO MULTITIMEFRAME ════════════════
f_trend(_tf) => request.security(syminfo.tickerid, _tf, close > ta.ema(close, emaLen), lookahead=barmerge.lookahead_off)
tendTF1 = f_trend(tf1)
tendTF2 = f_trend(tf2)
tendAlc = tendTF1 and (exigirMacro ? tendTF2 : true)
tendBaj = (not tendTF1) and (exigirMacro ? not tendTF2 : true)
gradoA  = tendTF1 == tendTF2

[volHTF, volMA, clvHTF] = request.security(syminfo.tickerid, tfVol, [volume, ta.sma(volume, volLen), ((close - low) - (high - close)) / math.max(high - low, syminfo.mintick)], lookahead=barmerge.lookahead_off)
vetoLong = volHTF > volMA * multVol and clvHTF < -clvMin
vetoShort = volHTF > volMA * multVol and clvHTF >  clvMin

enSesion = not usarSesion or not na(time(timeframe.period, sessLondres)) or not na(time(timeframe.period, sessNY))

// ════════════════ ESTRUCTURA Y GATILLO (VELA EXACTA) ════════════════
ph = ta.pivothigh(high, lenPivote, lenPivote)
pl = ta.pivotlow(low,  lenPivote, lenPivote)
var float swingHigh = na
var float swingLow  = na
if not na(ph)
    swingHigh := ph
if not na(pl)
    swingLow := pl

atr = ta.atr(14)
rng    = math.max(high - low, syminfo.mintick)
clvTrig = ((close - low) - (high - close)) / rng
conf    = barstate.isconfirmed   // ← anti-repintado: nada se imprime en vela viva

sweepLow  = conf and not na(swingLow)  and low  < swingLow  and close > swingLow
sweepHigh = conf and not na(swingHigh) and high > swingHigh and close < swingHigh
bosUp     = conf and not na(swingHigh) and close > swingHigh and close[1] <= swingHigh
bosDn     = conf and not na(swingLow)  and close < swingLow  and close[1] >= swingLow

dispAlc = clvTrig >=  clvTrigMin
dispBaj = clvTrig <= -clvTrigMin

var int lastSigBar = -100000
libre = bar_index - lastSigBar >= cooldown

sigLong  = conf and libre and enSesion and not vetoLong  and tendAlc and dispAlc and ((modoBarrido and sweepLow) or (modoBOS and bosUp))
sigShort = conf and libre and enSesion and not vetoShort and tendBaj and dispBaj and ((modoBarrido and sweepHigh) or (modoBOS and bosDn))
porBarridoL = modoBarrido and sweepLow
porBarridoS = modoBarrido and sweepHigh

// ════════════════ GESTIÓN: ME, PARCIALES, A SALVO, RUNNER ════════════════
var int   dir   = 0
var int   fase  = 0      // 1 abierta · 2 TP1 tocado · 3 a salvo
var float entry = na
var float me    = na
var float tp1   = na
var float tp2   = na
var float be    = na
var float trail = na
var float swept = na
var float hh    = na
var float ll    = na
var bool  invMarcada = false
var line lnEntry = na
var line lnTp1   = na
var line lnTp2   = na
var line lnTrail = na
var label lbEntry = na

f_ME(_dir) =>
    float base = metodoME == "ATR xN" ? atrME * atr : (not na(swingHigh) and not na(swingLow) ? swingHigh - swingLow : atrME * atr)
    math.max(base, 2.0 * atr)

f_limpiar() =>
    line.delete(lnEntry), line.delete(lnTp1), line.delete(lnTp2), line.delete(lnTrail), label.delete(lbEntry)

if sigLong and dir == 0
    f_limpiar()
    dir := 1, fase := 1, invMarcada := false
    entry := close, swept := swingLow, me := f_ME(1)
    tp1 := entry + me * pctTP1 / 100, tp2 := entry + me * pctTP2 / 100
    be := entry + beBufATR * atr, trail := swingLow, hh := high, ll := low
    lastSigBar := bar_index
    int tFin = time + timeframe.in_seconds() * 1000 * 40
    lnEntry := line.new(time, entry, tFin, entry, xloc=xloc.bar_time, color=color.blue, width=2)
    lnTp1   := line.new(time, tp1, tFin, tp1, xloc=xloc.bar_time, color=color.teal, style=line.style_dotted)
    lnTp2   := line.new(time, tp2, tFin, tp2, xloc=xloc.bar_time, color=color.teal, style=line.style_dotted)
    lnTrail := line.new(time, trail, tFin, trail, xloc=xloc.bar_time, color=color.orange, width=2)
    lbEntry := label.new(time, low, (porBarridoL ? " BARRIDO LONG" : "🚀 CONTINUACIÓN LONG") + (gradoA ? " (A+)" : " (B)"), xloc=xloc.bar_time, style=label.style_label_up, color=color.new(color.lime, 10), textcolor=color.black, size=size.small)

if sigShort and dir == 0
    f_limpiar()
    dir := -1, fase := 1, invMarcada := false
    entry := close, swept := swingHigh, me := f_ME(-1)
    tp1 := entry - me * pctTP1 / 100, tp2 := entry - me * pctTP2 / 100
    be := entry - beBufATR * atr, trail := swingHigh, hh := high, ll := low
    lastSigBar := bar_index
    int tFin = time + timeframe.in_seconds() * 1000 * 40
    lnEntry := line.new(time, entry, tFin, entry, xloc=xloc.bar_time, color=color.blue, width=2)
    lnTp1   := line.new(time, tp1, tFin, tp1, xloc=xloc.bar_time, color=color.teal, style=line.style_dotted)
    lnTp2   := line.new(time, tp2, tFin, tp2, xloc=xloc.bar_time, color=color.teal, style=line.style_dotted)
    lnTrail := line.new(time, trail, tFin, trail, xloc=xloc.bar_time, color=color.orange, width=2)
    lbEntry := label.new(time, high, (porBarridoS ? "🎯 BARRIDO SHORT" : "🚀 CONTINUACIÓN SHORT") + (gradoA ? " (A+)" : " (B)"), xloc=xloc.bar_time, style=label.style_label_down, color=color.new(color.red, 10), textcolor=color.white, size=size.small)

// ── Seguimiento de la operación abierta ──
evTP1 = false, evTP2 = false, evBE = false, evExit = false, evInv = false
if dir == 1 and conf
    hh := math.max(hh, high)
    if not na(pl)
        trail := math.max(trail, pl)
    if modoTrail == "Chandelier ATR"
        trail := math.max(trail, hh - atrTrail * atr)
    line.set_y1(lnTrail, trail), line.set_y2(lnTrail, trail), line.set_x2(lnTrail, time + timeframe.in_seconds() * 1000 * 40)
    if fase == 1 and high >= tp1
        fase := 2, evTP1 := true
        label.new(time, high, "💰 TP1 (" + str.tostring(pctTP1) + "%)\nCierra parcial → operación a salvo en " + str.tostring(be, "#.##"), xloc=xloc.bar_time, style=label.style_label_down, color=color.new(color.teal, 10), textcolor=color.white, size=size.tiny)
    if fase >= 2 and high >= tp2
        evTP2 := true
        label.new(time, high, "💰 TP2 (" + str.tostring(pctTP2) + "%) opcional", xloc=xloc.bar_time, style=label.style_label_down, color=color.new(color.teal, 30), textcolor=color.white, size=size.tiny)
    if fase == 2 and low <= be
        fase := 3, evBE := true
        label.new(time, low, "🛡️ A SALVO: riesgo ≈ 0, deja correr", xloc=xloc.bar_time, style=label.style_label_up, color=color.new(color.gray, 20), textcolor=color.white, size=size.tiny)
    if fase == 1 and close < swept and not invMarcada
        invMarcada := true, evInv := true
        label.new(time, low, "⚠️ Invalidación estructural (informativo: tú decides)", xloc=xloc.bar_time, style=label.style_label_up, color=color.new(color.orange, 20), textcolor=color.black, size=size.tiny)
    if close < trail
        evExit := true
        label.new(time, low, "🏁 Runner: cierre por " + modoTrail, xloc=xloc.bar_time, style=label.style_label_up, color=color.new(color.purple, 10), textcolor=color.white, size=size.small)
        dir := 0, f_limpiar()

if dir == -1 and conf
    ll := math.min(ll, low)
    if not na(ph)
        trail := math.min(trail, ph)
    if modoTrail == "Chandelier ATR"
        trail := math.min(trail, ll + atrTrail * atr)
    line.set_y1(lnTrail, trail), line.set_y2(lnTrail, trail), line.set_x2(lnTrail, time + timeframe.in_seconds() * 1000 * 40)
    if fase == 1 and low <= tp1
        fase := 2, evTP1 := true
        label.new(time, low, "💰 TP1 (" + str.tostring(pctTP1) + "%)\nCierra parcial → operación a salvo en " + str.tostring(be, "#.##"), xloc=xloc.bar_time, style=label.style_label_up, color=color.new(color.teal, 10), textcolor=color.white, size=size.tiny)
    if fase >= 2 and low <= tp2
        evTP2 := true
        label.new(time, low, "💰 TP2 (" + str.tostring(pctTP2) + "%) opcional", xloc=xloc.bar_time, style=label.style_label_up, color=color.new(color.teal, 30), textcolor=color.white, size=size.tiny)
    if fase == 2 and high >= be
        fase := 3, evBE := true
        label.new(time, high, "🛡️ A SALVO: riesgo ≈ 0, deja correr", xloc=xloc.bar_time, style=label.style_label_down, color=color.new(color.gray, 20), textcolor=color.white, size=size.tiny)
    if fase == 1 and close > swept and not invMarcada
        invMarcada := true, evInv := true
        label.new(time, high, "⚠️ Invalidación estructural (informativo: tú decides)", xloc=xloc.bar_time, style=label.style_label_down, color=color.new(color.orange, 20), textcolor=color.black, size=size.tiny)
    if close > trail
        evExit := true
        label.new(time, high, "🏁 Runner: cierre por " + modoTrail, xloc=xloc.bar_time, style=label.style_label_down, color=color.new(color.purple, 10), textcolor=color.white, size=size.small)
        dir := 0, f_limpiar()

// ── Marcas visuales en la vela exacta ──
plotshape(sigLong,  "ENTRADA LONG",  shape.triangleup,   location.belowbar, color.lime, size=size.small, text="LONG")
plotshape(sigShort, "ENTRADA SHORT", shape.triangledown, location.abovebar, color.red,  size=size.small, text="SHORT")
plotshape(sweepHigh and not sigShort, "Barrido H", shape.triangledown, location.abovebar, color.new(color.red, 60),  size=size.tiny)
plotshape(sweepLow  and not sigLong,  "Barrido L", shape.triangleup,   location.belowbar, color.new(color.lime, 60), size=size.tiny)

// ── Alertas (frecuencia: cierre de barra) ──
alertcondition(sigLong,  "ENTRADA LONG exacta",  "SQv3: LONG en vela confirmada. Tendencia multi-TF y volumen validados.")
alertcondition(sigShort, "ENTRADA SHORT exacta", "SQv3: SHORT en vela confirmada. Tendencia multi-TF y volumen validados.")
alertcondition(evTP1, "TP1 tocado → pasar a salvo", "SQv3: TP1 alcanzado. Cierra parcial y mueve a nivel a salvo.")
alertcondition(evBE,  "Operación a salvo", "SQv3: nivel a salvo tocado. Riesgo ≈ 0, runner libre.")
alertcondition(evExit,"Salida del runner", "SQv3: cierre del runner por estructura/trail.")

// ── Panel multi-TF ──
var table panel = table.new(position.top_right, 2, 7, bgcolor=color.new(color.black, 70), frame_width=1)
if barstate.islast
    table.cell(panel,0,0,"Tend " + tf1, text_color=color.white, text_size=size.small)
    table.cell(panel,1,0,tendTF1 ? "ALCISTA ▲" : "BAJISTA ▼", text_color=tendTF1 ? color.lime : color.red, text_size=size.small)
    table.cell(panel,0,1,"Tend " + tf2, text_color=color.white, text_size=size.small)
    table.cell(panel,1,1,tendTF2 ? "ALCISTA ▲" : "BAJISTA ▼", text_color=tendTF2 ? color.lime : color.red, text_size=size.small)
    table.cell(panel,0,2,"Grado señal", text_color=color.white, text_size=size.small)
    table.cell(panel,1,2,gradoA ? "A+ (TFs alineados)" : "B (solo TF1)", text_color=gradoA ? color.lime : color.yellow, text_size=size.small)
    table.cell(panel,0,3,"Sesión", text_color=color.white, text_size=size.small)
    table.cell(panel,1,3,enSesion ? "Activa ✅" : "Muerta ⛔", text_color=enSesion ? color.aqua : color.gray, text_size=size.small)
    table.cell(panel,0,4,"Vol/CLV HTF", text_color=color.white, text_size=size.small)
    table.cell(panel,1,4,(vetoLong ? "VETO short-side" : vetoShort ? "VETO long-side" : "Sin veto") + " · CLV " + str.tostring(clvHTF, "#.##"), text_color=vetoLong or vetoShort ? color.orange : color.gray, text_size=size.small)
    table.cell(panel,0,5,"CLV gatillo", text_color=color.white, text_size=size.small)
    table.cell(panel,1,5,str.tostring(clvTrig, "#.##"), text_color=clvTrig >= clvTrigMin ? color.lime : clvTrig <= -clvTrigMin ? color.red : color.gray, text_size=size.small)
    table.cell(panel,0,6,"Estado trade", text_color=color.white, text_size=size.small)
    table.cell(panel,1,6,dir == 0 ? "Sin posición" : (dir == 1 ? "LONG " : "SHORT ") + (fase == 1 ? "abierta" : fase == 2 ? "→ a salvo" : "a salvo 🛡️"), text_color=dir == 1 ? color.lime : dir == -1 ? color.red : color.gray, text_size=size.small)








