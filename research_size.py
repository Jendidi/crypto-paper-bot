"""Effet de la taille des positions sur la stratégie blend (rendement, baisse maximale, risque par trade)."""
import numpy as np
import pandas as pd

import config
from backtest_blend import run
from engine import net_returns, stats
from strategy import cap_gross

closes, w, net = run()
split = closes.index[int(len(closes) * (1 - config.OUT_OF_SAMPLE))]
print(f"{'taille':>8} {'tout':^30} | {'avant':^22} | {'après':^22} | {'investi':>7} {'risque/trade RSI2':>18}")
for k in (1.0, 1.5, 2.0, 2.5, 3.0):
    wk = cap_gross(w * k)
    n = net_returns(wk, closes, "1d")
    cols = []
    for mask in (slice(None), n.index < split, n.index >= split):
        s = stats(n[mask], wk[mask], "1d")
        cols.append(s)
    f = lambda s: f"{s['cagr']:>+6.1%} Sh{s['sharpe']:>5.2f} DD{s['dd']:>5.0%}"
    print(f"{k:>7.1f}x {f(cols[0]):^30} | {f(cols[1]):^22} | {f(cols[2]):^22} | {wk.abs().sum(axis=1).mean():>7.0%} {k:>17.1f} %")
gross = cap_gross(w * 2.0).abs().sum(axis=1)
print(f"\nÀ x2 : capital investi au maximum {gross.max():.0%}, plafonné à 100 % ({(gross >= 0.999).mean():.1%} du temps)")
