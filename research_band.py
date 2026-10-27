"""Effet d'une « bande sans ordre » : on ne bouge une position que si l'écart avec la cible dépasse X % du capital."""
import numpy as np
import pandas as pd

import config
from backtest_blend import run
from engine import net_returns, stats


def with_band(w, band):
    """Sorties toujours autorisées ; entrées et ajustements seulement au-delà de `band`."""
    if band <= 0:
        return w
    out = np.zeros(w.shape)
    cur = np.zeros(w.shape[1])
    for i, target in enumerate(w.to_numpy()):
        move = np.abs(target - cur)
        change = ((move >= band) | ((target == 0) & (cur > 0)))
        cur = np.where(change, target, cur)
        out[i] = cur
    return pd.DataFrame(out, index=w.index, columns=w.columns)


closes, w, _ = run(2.0)
split = closes.index[int(len(closes) * (1 - config.OUT_OF_SAMPLE))]
print(f"{'bande':>7} {'tout':^30} | {'après':^22} | {'ordres/sem':>10} {'positions < 2 %':>16}")
for band in (0.0, 0.01, 0.02, 0.03):
    wb = with_band(w, band)
    n = net_returns(wb, closes, "1d")
    a, b = stats(n, wb, "1d"), stats(n[n.index >= split], wb[wb.index >= split], "1d")
    orders = (wb.diff().abs() > 1e-4).sum().sum() / (len(wb) / 7)
    small = ((wb > 0) & (wb < 0.02)).sum().sum() / max((wb > 0).sum().sum(), 1)
    f = lambda s: f"{s['cagr']:>+6.1%} Sh{s['sharpe']:>5.2f} DD{s['dd']:>5.0%}"
    print(f"{band:>7.0%} {f(a):^30} | {f(b):^22} | {orders:>10.1f} {small:>16.0%}")
