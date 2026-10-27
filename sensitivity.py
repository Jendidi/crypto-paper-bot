"""Robustesse du suivi de tendance « long seul » : réglages voisins et jour de rééquilibrage."""
import pandas as pd

import config
from engine import net_returns, stats
from research import daily_closes
from strategy import tsmom

closes = daily_closes().dropna()
split = closes.index[int(len(closes) * (1 - config.OUT_OF_SAMPLE))]


def sharpe_cagr(**kw):
    kw = dict(kw)
    if "offset" in kw:
        kw["rebalance_weekday"] = kw.pop("offset")
    if kw.pop("rebalance_days", 7) != 7:
        raise ValueError("sensitivity.py ne teste que le rééquilibrage hebdomadaire")
    w = tsmom(closes, long_only=True, **kw)
    s = stats(net_returns(w, closes, "1d"), w, "1d")
    return s["sharpe"], s["cagr"], s["dd"]


print("Long seul, Sharpe / rendement annuel / pire baisse (période complète)")
sets = {"20-200": (20, 50, 100, 200), "10-100": (10, 20, 50, 100), "50-200": (50, 100, 200), "30-90": (30, 60, 90)}
print(f"{'lookbacks':10}{'rééquilibrage hebdo (lundi)':>30}")
for lbl, lb in sets.items():
    cells = []
    for reb in (7,):
        sh, cg, dd = sharpe_cagr(lookbacks=lb, rebalance_days=reb)
        cells.append(f"{sh:5.2f} / {cg:+6.1%} / {dd:5.0%}")
    print(f"{lbl:10}" + "".join(f"{c:>26}" for c in cells))

print("\nRéglage retenu (20-200, hebdo) selon le jour de la semaine du rééquilibrage")
res = [sharpe_cagr(offset=o) for o in range(7)]
print("Sharpe :", " ".join(f"{r[0]:.2f}" for r in res), f"| min {min(r[0] for r in res):.2f}, max {max(r[0] for r in res):.2f}")
print("Rdt/an :", " ".join(f"{r[1]:+.0%}" for r in res))
print("Pire DD:", " ".join(f"{r[2]:.0%}" for r in res))

print("\nSensibilité à la cible de volatilité (0 = pas de réduction, poids égaux)")
for vt in (0.4, 0.6, 1.0, 5.0):
    sh, cg, dd = sharpe_cagr(vol_target=vt)
    print(f"vol_target {vt:>3}: Sharpe {sh:.2f}, rdt/an {cg:+.1%}, DD {dd:.0%}")
