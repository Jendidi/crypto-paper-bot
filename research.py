"""Banc d'essai du momentum de série temporelle (strategy.tsmom) en bougies journalières.

Les paramètres sont ceux de la littérature, fixés avant de regarder les résultats.
La grille de sensibilité (sensitivity.py) sert à vérifier la robustesse, pas à
choisir les meilleurs réglages.

Usage :  python research.py
"""
import pandas as pd

import config
from data import CACHE, fetch_history, resample
from engine import hold_stats, net_returns, stats
from strategy import tsmom


def daily_closes(refresh=False):
    """Clôtures journalières. Lit le cache local (data/) sauf si refresh=True."""
    def hist(s):
        path = CACHE / f"{s.replace('/', '_')}_1h.csv"
        if refresh or not path.exists():
            return fetch_history(s)
        return pd.read_csv(path, index_col="ts", parse_dates=True)
    return pd.DataFrame({s: resample(hist(s), "1d")["close"] for s in config.SYMBOLS})


VARIANTS = {
    "tsmom long/short": dict(),
    "tsmom long seul": dict(long_only=True),
}


def report(closes, name, w, split):
    net = net_returns(w, closes, "1d")
    out = []
    for label, mask in (("tout", slice(None)), ("avant", net.index < split), ("après", net.index >= split)):
        s = stats(net[mask], w[mask], "1d")
        out.append(f"{label} {s['cagr']:+6.1%} (Sharpe {s['sharpe']:+.2f}, DD {s['dd']:.0%})")
    yearly = (1 + net).groupby(net.index.year).prod() - 1
    yrs = "  ".join(f"{y}: {r:+.0%}" for y, r in yearly.items())
    print(f"{name:20} " + " | ".join(out) + f"\n{'':20} par année -> {yrs}")


if __name__ == "__main__":
    closes = daily_closes().dropna()
    split = closes.index[int(len(closes) * (1 - config.OUT_OF_SAMPLE))]
    print(f"{closes.index[0]:%Y-%m-%d} -> {closes.index[-1]:%Y-%m-%d} | « après » depuis le {split:%Y-%m-%d}\n")
    for name, kw in VARIANTS.items():
        report(closes, name, tsmom(closes, **kw), split)
    print()
    for name, s in hold_stats(closes, "1d").items():
        print(f"{name:20} {s['cagr']:+6.1%} (Sharpe {s['sharpe']:+.2f}, DD {s['dd']:.0%})")
