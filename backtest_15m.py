"""Backtest 15 minutes de la stratégie blend, comparé à la version journalière sur la MÊME période.

Usage :  python backtest_15m.py          (nécessite download_15m.py)
"""
import numpy as np
import pandas as pd

import backtest_blend
import config
import intraday
from data import fetch_daily, fetch_history
from engine import net_returns, stats


def daily_stats(net, w):
    nd = (1 + net).resample("1D").prod() - 1
    return stats(nd, w.resample("1D").last(), "1d")


def show(label, net, w, split, weeks):
    cols = []
    for mask in (np.ones(len(net), bool), net.index < split, net.index >= split):
        s = daily_stats(net[mask], w[mask])
        cols.append(f"{s['cagr']:>+6.1%} Sh{s['sharpe']:>5.2f} DD{s['dd']:>5.0%}")
    orders = (w.diff().abs() > 1e-4).sum().sum() / weeks
    print(f"{label:30} " + " | ".join(f"{c:^22}" for c in cols) + f" | {orders:>5.1f} ordres/sem | investi {w.abs().sum(axis=1).mean():.0%}")


VARIANTS = [
    ("15 min complet", dict()),
    ("entrées à minuit, sorties 15 min", dict(entry_close_only=True)),
    ("entrées + rebond à minuit, stop 15 min", dict(entry_close_only=True, rebound_close_only=True)),
]


def main():
    bars1d = {s: fetch_daily(f"{s.split('/')[0]}/USDT") for s in config.SYMBOLS}
    bars15 = {s: fetch_history(s, days=730, interval="15m") for s in config.SYMBOLS}
    closes15 = pd.DataFrame({s: b["close"] for s, b in bars15.items()}).dropna()
    split = closes15.index[int(len(closes15) * 0.6)]
    print(f"{len(config.SYMBOLS)} cryptos : {closes15.index[0]:%Y-%m-%d} -> {closes15.index[-1]:%Y-%m-%d} | coupure {split:%Y-%m-%d}")
    print(f"{'':30} {'tout':^22} | {'avant':^22} | {'après':^22}")
    for label, kw in VARIANTS:
        w15, c15 = intraday.weights15(bars15, bars1d, size=2.0, **kw)
        show(label, net_returns(w15, c15, "15m"), w15, split, len(w15) / (96 * 7))
    closes, wd, netd = backtest_blend.run(2.0)
    m = netd.index >= closes15.index[0].normalize()
    show("journalier (référence)", netd[m], wd[m], split, m.sum() / 7)
    btc = closes15.iloc[:, 0]
    print(f"BTC gardé sur la période : {(btc.iloc[-1] / btc.iloc[0]) ** (365 / (btc.index[-1] - btc.index[0]).days) - 1:+.1%}/an")


if __name__ == "__main__":
    main()
