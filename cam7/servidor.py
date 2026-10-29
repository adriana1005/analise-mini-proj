#!/usr/bin/env python3
"""Servidor Flask: ingestão, estatísticas online, alertas e SSE para o dashboard."""
import csv, json, math, queue, threading, time
from collections import deque
from datetime import datetime, timezone
from flask import Flask, Response, jsonify, request

try:
    import psutil
    PROC = psutil.Process()
except ImportError:
    PROC = None

# ---------------- parâmetros do grupo (semente 107335) ----------------
SEMENTE = 107335
SETPOINT = 1.0 + (SEMENTE % 5) * 0.5
CFG = {"lim_sup": SETPOINT + 2.0, "lim_inf": SETPOINT - 2.0, "persistencia_min": 2.0}

# ---------------- constantes de afinação (tempo SIMULADO, em segundos) ----------------
ALFA = 0.1               # EWMA
JAN_STATS_S = 300        # janela de 5 min
JAN_TEND_S = 1800        # janela da regressão (30 min)
TAU_TEND_S = 600         # suavização da tendência (10 min)
LIM_TEND = 0.25          # °C/h
HIST_TEND = 0.10         # histerese da tendência
PERS_TEND_S = 300        # persistência da R3
GRACA_PORTA_S = 480      # tolerância depois de a porta fechar
PORTA_AVISO_S = 120
HISTERESE = 0.5          # °C (R2)
SILENCIO_S = 10          # segundos REAIS (R5)

app = Flask(__name__, static_folder="static", static_url_path="")
LOCK = threading.RLock()
CLIENTES = set()

f_reg = open("registo.csv", "w", newline="", encoding="utf-8")
w_reg = csv.writer(f_reg)
w_reg.writerow(["ts", "temp", "ewma", "tendencia", "porta", "seq"])
f_al = open("alertas_log.csv", "w", newline="", encoding="utf-8")
w_al = csv.writer(f_al)
w_al.writerow(["ts", "evento", "id", "regra", "nivel", "msg"])


def iso(ts):
    return datetime.fromtimestamp(ts or 0, timezone.utc).isoformat(timespec="milliseconds")


def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def broadcast(obj):
    d = json.dumps(obj)
    for q in list(CLIENTES):
        try:
            q.put_nowait(d)
        except queue.Full:
            pass


class Camara:
    def __init__(self):
        self.cont = dict(recebidas=0, validas=0, rejeitadas=0, malformadas=0,
                         duplicadas=0, desordenadas=0)
        self.vistos, self.vistos_fila = set(), deque()
        self.max_seq, self.em_falta = None, set()
        # Welford + min/max
        self.n, self.media, self.m2, self.tmin, self.tmax = 0, 0.0, 0.0, None, None
        # janelas (todas limitadas)
        self.j5 = deque(maxlen=5000)
        self.jt = deque(maxlen=5000)
        self.ult30 = deque(maxlen=30)
        self.res_rej = deque(maxlen=60)
        self.hist = deque(maxlen=2500)           # para o gráfico do browser
        self.alertas = deque(maxlen=200)
        self.ativos, self.prox_id = {}, 1
        self.ewma = None
        self.slope_raw, self.slope, self.slope_t, self.tend_ok = None, 0.0, None, False
        self.ts_ult, self.ts_prev = None, None
        self.porta, self.porta_desde, self.porta_fechou = False, None, None
        self.acum = {"R1": 0.0, "R3": 0.0}
        self.temp = self.hum = None
        self.ultima_real = None

    # ---------- alertas ----------
    def abrir(self, regra, nivel, msg, ts):
        if regra in self.ativos:                 # nunca repetir enquanto o anterior está ativo
            return
        a = dict(id=self.prox_id, regra=regra, nivel=nivel, msg=msg,
                 inicio=ts, fim=None, estado="ativo")
        self.prox_id += 1
        self.ativos[regra] = a
        self.alertas.append(a)
        w_al.writerow([iso(ts), "abre", a["id"], regra, nivel, msg]); f_al.flush()

    def fechar(self, regra, ts):
        a = self.ativos.pop(regra, None)
        if a:
            a["estado"], a["fim"] = "resolvido", ts
            w_al.writerow([iso(ts), "fecha", a["id"], regra, a["nivel"], a["msg"]]); f_al.flush()

    def tolerante(self, ts):
        return self.porta or (self.porta_fechou is not None and ts - self.porta_fechou < GRACA_PORTA_S)

    # ---------- ingestão ----------
    def processar(self, m):
        c = self.cont
        c["recebidas"] += 1
        self.ultima_real = time.monotonic()
        self.fechar("R5-silencio", self.ts_ult)          # chegou mensagem → silêncio acabou

        # 1) esquema
        try:
            seq = m["seq"]
            ts = datetime.fromisoformat(m["ts"].replace("Z", "+00:00")).timestamp()
            porta, temp, hum = m["porta_aberta"], m["temperatura_c"], m["humidade_pct"]
            if type(seq) is not int or type(porta) is not bool or not isinstance(m["sensor_id"], str):
                raise ValueError
        except (KeyError, ValueError, TypeError, AttributeError):
            c["malformadas"] += 1
            return None

        # 2) duplicados e sequência
        if seq in self.vistos:
            c["duplicadas"] += 1
            return None
        self.vistos.add(seq); self.vistos_fila.append(seq)
        if len(self.vistos_fila) > 2000:
            self.vistos.discard(self.vistos_fila.popleft())
        if self.max_seq is None or seq > self.max_seq:
            if self.max_seq is not None and seq > self.max_seq + 1:
                self.em_falta.update(range(max(self.max_seq + 1, seq - 1000), seq))
            self.max_seq = seq
            if len(self.em_falta) > 5000:
                self.em_falta = {s for s in self.em_falta if s > seq - 5000}
        else:
            self.em_falta.discard(seq)                   # chegou atrasada
            c["desordenadas"] += 1
        if self.ts_ult is not None and ts <= self.ts_ult:   # fora de ordem: não entra nas estatísticas
            return None
        self.ts_ult = ts

        # 3) porta (R4) – válida mesmo que a temperatura não seja
        self._porta(porta, ts)

        # 4) validação física + taxa de rejeição (R5)
        ok = num(temp) and -30 <= temp <= 50 and num(hum) and 0 <= hum <= 100
        self.res_rej.append(0 if ok else 1)
        if len(self.res_rej) >= 20:
            taxa = sum(self.res_rej) / len(self.res_rej)
            if taxa > 0.05:
                self.abrir("R5-rejeicoes", "AVISO", f"{taxa:.0%} das leituras rejeitadas", ts)
            elif taxa <= 0.02:
                self.fechar("R5-rejeicoes", ts)
        if not ok:
            c["rejeitadas"] += 1
            return None

        c["validas"] += 1
        x = float(temp)
        self.temp, self.hum = x, float(hum)

        # 5) valor preso (R5): 30 leituras iguais → não fiável, não entra nas estatísticas
        self.ult30.append(x)
        preso = len(self.ult30) == 30 and max(self.ult30) == min(self.ult30)
        if preso:
            self.abrir("R5-preso", "AVISO", "Valor preso: 30 leituras idênticas", ts)
        else:
            self.fechar("R5-preso", ts)
            self._estatisticas(x, ts)

        ponto = dict(t=ts, temp=x, ewma=self.ewma, porta=porta, hum=self.hum,
                     seq=seq, env=m.get("t_envio_ms"))
        self.hist.append(ponto)
        w_reg.writerow([iso(ts), x, self.ewma, self.slope if self.tend_ok else "", int(porta), seq])
        f_reg.flush()
        return ponto

    def _porta(self, aberta, ts):
        if aberta and not self.porta:
            self.porta, self.porta_desde = True, ts
            self.abrir("R4-info", "INFO", "Porta aberta", ts)
        elif not aberta and self.porta:
            self.porta, self.porta_fechou = False, ts
            self.fechar("R4-info", ts); self.fechar("R4-aviso", ts)
        if self.porta and ts - self.porta_desde > PORTA_AVISO_S:
            self.abrir("R4-aviso", "AVISO", "Porta aberta há mais de 2 min", ts)

    # ---------- estatísticas incrementais ----------
    def _estatisticas(self, x, ts):
        self.n += 1                                       # Welford
        d = x - self.media
        self.media += d / self.n
        self.m2 += d * (x - self.media)
        self.tmin = x if self.tmin is None else min(self.tmin, x)
        self.tmax = x if self.tmax is None else max(self.tmax, x)

        self.j5.append((ts, x))                           # janela de 5 min
        while ts - self.j5[0][0] > JAN_STATS_S:
            self.j5.popleft()

        self.ewma = x if self.ewma is None else ALFA * x + (1 - ALFA) * self.ewma

        tol = self.tolerante(ts)
        if not tol:                                       # a tendência ignora períodos de porta
            self.jt.append((ts, x))
        while self.jt and ts - self.jt[0][0] > JAN_TEND_S:
            self.jt.popleft()
        self._tendencia(ts)
        self._regras(ts, tol)

    def _tendencia(self, ts):
        jt = self.jt
        if len(jt) >= 15 and jt[-1][0] - jt[0][0] >= 1200:
            n = len(jt)
            tm = sum(t for t, _ in jt) / n
            xm = sum(v for _, v in jt) / n
            sxx = sum((t - tm) ** 2 for t, _ in jt)
            sxy = sum((t - tm) * (v - xm) for t, v in jt)
            self.slope_raw = sxy / sxx * 3600             # °C/h
            dt = 0.0 if self.slope_t is None else ts - self.slope_t
            self.slope += (1 - math.exp(-dt / TAU_TEND_S)) * (self.slope_raw - self.slope)
            self.slope_t, self.tend_ok = ts, True
        else:
            self.slope_raw = None

    # ---------- regras R1 e R3 ----------
    def _regras(self, ts, tol):
        dt = 0.0 if self.ts_prev is None else ts - self.ts_prev
        self.ts_prev = ts
        sup, inf, N = CFG["lim_sup"], CFG["lim_inf"], CFG["persistencia_min"] * 60
        e = self.ewma

        # R1 + R2: limite com persistência e histerese (conta só fora do período de porta)
        if "R1" in self.ativos:
            if inf + HISTERESE <= e <= sup - HISTERESE:
                self.fechar("R1", ts); self.acum["R1"] = 0.0
        elif e > sup or e < inf:
            if not tol:
                self.acum["R1"] += dt
            if self.acum["R1"] >= N:
                self.abrir("R1", "CRÍTICO",
                           f"Temperatura (EWMA {e:.2f} °C) fora dos limites há {N/60:.1f} min", ts)
        else:
            self.acum["R1"] = 0.0

        # R3: tendência de subida, só conta com a porta fechada
        if "R3" in self.ativos:
            if self.slope < LIM_TEND - HIST_TEND:
                self.fechar("R3", ts); self.acum["R3"] = 0.0
        elif self.tend_ok and self.slope > LIM_TEND:
            if not tol:
                self.acum["R3"] += dt
            if self.acum["R3"] >= PERS_TEND_S and not tol:
                self.abrir("R3", "AVISO", f"Subida anormal: {self.slope:+.2f} °C/h", ts)
        else:
            self.acum["R3"] = 0.0

    # ---------- snapshot para o browser ----------
    def snapshot(self, tipo, ponto=None):
        niv = {a["nivel"] for a in self.ativos.values()}
        estado = "CRÍTICO" if "CRÍTICO" in niv else "AVISO" if "AVISO" in niv else "OK"
        v = [x for _, x in self.j5]
        j5 = None
        if len(v) > 1:
            m = sum(v) / len(v)
            j5 = dict(media=m, dp=math.sqrt(sum((a - m) ** 2 for a in v) / (len(v) - 1)),
                      min=min(v), max=max(v))
        perdidas = sum(1 for s in self.em_falta if s < (self.max_seq or 0) - 3)
        return {
            "tipo": tipo, "ponto": ponto, "estado": estado,
            "silencio": "R5-silencio" in self.ativos,
            "ha_s": None if self.ultima_real is None else time.monotonic() - self.ultima_real,
            "kpi": {
                "temp": self.temp, "ewma": self.ewma, "hum": self.hum, "porta": self.porta,
                "tend": self.slope if self.tend_ok else None,
                "ativos": sum(1 for a in self.ativos.values() if a["nivel"] != "INFO"),
                "media": self.media if self.n else None,
                "dp": math.sqrt(self.m2 / (self.n - 1)) if self.n > 1 else None,
                "min": self.tmin, "max": self.tmax, "j5": j5,
            },
            "cfg": CFG,
            "alertas": list(self.alertas)[-50:][::-1],
            "sessao": dict(self.cont, perdidas=perdidas,
                           rss_mb=round(PROC.memory_info().rss / 1e6, 1) if PROC else None),
        }


CAM = Camara()


# ---------------- rotas ----------------
@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.post("/ingest")
def ingest():
    m = request.get_json(silent=True)
    with LOCK:
        if not isinstance(m, dict):
            CAM.cont["recebidas"] += 1
            CAM.cont["malformadas"] += 1
            return "", 400
        ponto = CAM.processar(m)
        broadcast(CAM.snapshot("leitura", ponto))
    return "", 204


@app.get("/stream")
def stream():
    q = queue.Queue(maxsize=500)
    with LOCK:
        snap = CAM.snapshot("init")
        snap["hist"] = list(CAM.hist)
        CLIENTES.add(q)
    q.put(json.dumps(snap))

    def gen():
        try:
            yield "retry: 1000\n\n"
            while True:
                try:
                    yield f"data: {q.get(timeout=15)}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            CLIENTES.discard(q)

    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/config")
def config():
    d = request.get_json(silent=True) or {}
    try:
        sup, inf, n = float(d["lim_sup"]), float(d["lim_inf"]), float(d["persistencia_min"])
    except (KeyError, TypeError, ValueError):
        return jsonify(erro="valores inválidos"), 400
    if not (sup - inf > 2 * HISTERESE and 0 < n <= 60):
        return jsonify(erro="valores incoerentes"), 400
    with LOCK:
        CFG.update(lim_sup=sup, lim_inf=inf, persistencia_min=n)
        broadcast(CAM.snapshot("estado"))
    return jsonify(CFG)


@app.post("/ack/<int:aid>")
def ack(aid):
    with LOCK:
        for a in CAM.ativos.values():
            if a["id"] == aid and a["estado"] == "ativo":
                a["estado"] = "reconhecido"
        broadcast(CAM.snapshot("estado"))
    return "", 204


def vigia():
    """Deteta silêncio com o relógio REAL do servidor e mantém o dashboard a receber estado."""
    while True:
        time.sleep(1)
        with LOCK:
            if CAM.ultima_real is None:
                continue
            ha = time.monotonic() - CAM.ultima_real
            if ha > SILENCIO_S:
                CAM.abrir("R5-silencio", "CRÍTICO",
                          f"Sensor sem comunicação há mais de {SILENCIO_S} s", CAM.ts_ult)
            if ha > 1.5:
                broadcast(CAM.snapshot("estado"))


if __name__ == "__main__":
    threading.Thread(target=vigia, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, threaded=True, use_reloader=False)