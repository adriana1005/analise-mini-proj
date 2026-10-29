#!/usr/bin/env python3
"""Corre depois do demo: python grafico.py  →  grafico_demo.png"""
import csv
from datetime import datetime, timedelta, timezone
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

SEM = 107335
SETPOINT = 1.0 + (SEM % 5) * 0.5
SUP, INF = SETPOINT + 2, SETPOINT - 2
T0 = datetime(2026, 11, 5, 14, 0, tzinfo=timezone.utc)
AVARIA = T0 + timedelta(minutes=20 + SEM % 25)


def t(s):
    return datetime.fromisoformat(s)


ts, temp, ewma, porta = [], [], [], []
with open("demo/registo.csv", encoding="utf-8") as fh:
    for r in csv.DictReader(fh):
        ts.append(t(r["ts"])); temp.append(float(r["temp"]))
        ewma.append(float(r["ewma"]) if r["ewma"] else None); porta.append(r["porta"] == "1")

fig, ax = plt.subplots(figsize=(13, 5.5))
ax.plot(ts, temp, lw=.8, color="#1565c0", label="Temperatura")
ax.plot(ts, ewma, lw=2, color="#ef6c00", label="EWMA")
ax.axhline(SUP, color="#c62828", ls="--", label="Limites")
ax.axhline(INF, color="#c62828", ls="--")
ax.axvline(AVARIA, color="k", ls=":", label="Início real da avaria")

ini = None                                           # faixas de porta aberta
for i, p in enumerate(porta):
    if p and ini is None: ini = ts[i]
    if (not p or i == len(porta) - 1) and ini is not None:
        ax.axvspan(ini, ts[i], color="grey", alpha=.25); ini = None

cores = {"AVISO": "#f9a825", "CRÍTICO": "#c62828"}
with open("demo/alertas_log.csv", encoding="utf-8") as fh:
    for r in csv.DictReader(fh):
        if r["evento"] == "abre" and r["nivel"] in cores:
            x = t(r["ts"])
            ax.axvline(x, color=cores[r["nivel"]], lw=1.5)
            ax.text(x, ax.get_ylim()[1], r["regra"], rotation=90, va="top", fontsize=7)

ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
ax.set_ylabel("°C"); ax.set_title("Câmara 7 · cenário demo (semente 107335)")
ax.legend(loc="upper left", fontsize=8)
fig.tight_layout(); fig.savefig("grafico_demo.png", dpi=150)
print("grafico_demo.png gravado")