#!/usr/bin/env python3
"""Simulador do sensor CAM07-T01.
Exemplo: python simulador.py --cenario demo --velocidade 20"""
import argparse, math, random, time
from datetime import datetime, timedelta, timezone
import requests

INICIO = datetime(2026, 11, 5, 14, 0, 0, tzinfo=timezone.utc)
FALHA_INI, FALHA_FIM = 60 * 60, 75 * 60          # janela da falha de sensor (s simulados)


def parametros(sem):
    return {
        "setpoint": 1.0 + (sem % 5) * 0.5,
        "sigma": 0.10 + (sem % 4) * 0.05,
        "intervalo_porta_min": 8 + (sem % 8),
        "inicio_avaria_min": 20 + (sem % 25),
        "falha_demo": ("preso", "picos", "silencio")[sem % 3],
        "periodo_comp_min": 12 + (sem % 9),          # 12..20 min
        "taxa_avaria": 0.3 + (sem % 4) * 0.1,        # 0,3..0,6 °C/h
    }


def dente_de_serra(t, periodo):
    """Sobe devagar (70% do ciclo), desce depressa. Devolve valor em [-1, 1]."""
    p = (t % periodo) / periodo
    return -1 + 2 * p / 0.7 if p < 0.7 else 1 - 2 * (p - 0.7) / 0.3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--semente", type=int, default=107335)
    ap.add_argument("--velocidade", type=float, default=1.0,
                    help="segundos simulados por leitura (60 = 1 min simulado por s real)")
    ap.add_argument("--cenario", choices=["livre", "demo"], default="livre")
    ap.add_argument("--url", default="http://127.0.0.1:5000/ingest")
    ap.add_argument("--falha", choices=["auto", "nenhuma", "preso", "picos", "silencio"], default="auto")
    ap.add_argument("--sem-portas", action="store_true")
    ap.add_argument("--sem-avaria", action="store_true")
    ap.add_argument("--sem-duplicados", action="store_true")
    a = ap.parse_args()

    P = parametros(a.semente)
    rng = random.Random(a.semente)
    falha = P["falha_demo"] if a.falha == "auto" else a.falha
    duracao = 120 * 60 if a.cenario == "demo" else None
    dt = a.velocidade
    sess = requests.Session()

    t, seq = 0.0, 0
    porta, porta_fim = False, 0.0
    prox_porta = rng.uniform(0.6, 1.4) * P["intervalo_porta_min"] * 60
    bump, preso_val = 0.0, None
    silencio_feito = avaria_ativa = falha_ativa = False
    retido = None

    def log(txt):
        print(f"[sim {timedelta(seconds=int(t))}] {txt}", flush=True)

    def enviar(m):
        m = dict(m, t_envio_ms=int(time.time() * 1000))   # campo extra, para medir latência
        try:
            sess.post(a.url, json=m, timeout=2)
        except requests.RequestException as e:
            print("erro de envio:", e)

    print("parâmetros:", P, "| falha:", falha, flush=True)

    while duracao is None or t < duracao:
        inicio_tick = time.monotonic()
        t += dt

        # --- porta (intervalos entre 0,6x e 1,4x da média → no demo há sempre >= 3 aberturas)
        if not a.sem_portas:
            if not porta and t >= prox_porta:
                porta, porta_fim = True, t + rng.uniform(30, 180)
                log("PORTA ABRE")
            elif porta and t >= porta_fim:
                porta = False
                prox_porta = t + rng.uniform(0.6, 1.4) * P["intervalo_porta_min"] * 60
                log("PORTA FECHA")
        # sobe até +3 °C com a porta aberta; recupera em ~8 min depois de fechar
        if porta:
            bump += (3.0 - bump) * (1 - math.exp(-dt / 60))
        else:
            bump *= math.exp(-dt / 100)

        # --- avaria do compressor: deriva lenta por cima do normal
        deriva = 0.0
        if not a.sem_avaria and t >= P["inicio_avaria_min"] * 60:
            deriva = P["taxa_avaria"] * (t - P["inicio_avaria_min"] * 60) / 3600
            if not avaria_ativa:
                avaria_ativa = True
                log(f"AVARIA DO COMPRESSOR COMEÇA ({P['taxa_avaria']} °C/h)")

        # --- falha de sensor
        em_falha = falha != "nenhuma" and FALHA_INI <= t < FALHA_FIM
        if em_falha and not falha_ativa:
            falha_ativa = True
            log(f"FALHA DE SENSOR ({falha}) COMEÇA")
        if falha == "silencio" and t >= FALHA_INI and not silencio_feito:
            silencio_feito = True
            pausa = rng.uniform(20, 60)
            log(f"SILÊNCIO de {pausa:.0f} s reais")
            time.sleep(pausa)
            inicio_tick = time.monotonic()

        # --- valores
        limpo = (P["setpoint"] + 0.4 * dente_de_serra(t, P["periodo_comp_min"] * 60)
                 + bump + deriva)
        temp = round(limpo + rng.gauss(0, P["sigma"]), 2)
        hum = (91.5 - 1.2 * (limpo - P["setpoint"]) + math.sin(2 * math.pi * t / 5400)
               + rng.gauss(0, 0.15))
        hum = round(min(95.0, max(88.0, hum)), 1)

        if em_falha and falha == "preso":
            if preso_val is None:
                preso_val = temp
            temp = preso_val
        elif em_falha and falha == "picos" and rng.random() < 0.15:
            temp = rng.choice([-40.0, 85.0, None])

        seq += 1
        msg = {
            "sensor_id": "CAM07-T01",
            "seq": seq,
            "ts": (INICIO + timedelta(seconds=t)).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "temperatura_c": temp,
            "humidade_pct": hum,
            "porta_aberta": porta,
        }

        # --- duplicados (1%) e desordem (1%: troca com a seguinte)
        r = 1.0 if a.sem_duplicados else rng.random()
        if retido is not None:
            enviar(msg); enviar(retido); retido = None
        elif r < 0.01:
            enviar(msg); enviar(msg)
        elif r < 0.02:
            retido = msg
        else:
            enviar(msg)

        time.sleep(max(0.0, 1.0 - (time.monotonic() - inicio_tick)))

    print("fim do cenário", flush=True)


if __name__ == "__main__":
    main()