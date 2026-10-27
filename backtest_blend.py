"""Backtest de la stratégie déployée (strategy.blend) sur les 25 cryptos, en bougies journalières.

Usage :  python backtest_blend.py
"""
import numpy as np
import pandas as pd

import config
from data import fetch_daily
from engine import net_returns, stats
from strategy import blend

START = "2022-10-27"


def run(size=2.0, band=None):
    """Rejoue la stratégie sur tout l'historique avec une taille fixe (x2 par défaut : la taille déployée)
    et la bande sans ordre déployée (config.NO_TRADE_BAND) appliquée dès le début."""
    band = config.NO_TRADE_BAND if band is None else band
    names = [s.split("/")[0] for s in config.SYMBOLS]
    bars = {n: fetch_daily(f"{n}/USDT") for n in names}
    closes = pd.DataFrame({n: d["close"] for n, d in bars.items()}).loc[START:]
    bars = {n: d.loc[closes.index[0]:] for n, d in bars.items()}
    w = blend(closes, bars, size=size, band=band).reindex(closes.index).fillna(0.0)
    return closes, w, net_returns(w, closes, "1d")


def summary(size=2.0):
    closes, w, net = run(size)
    split = closes.index[int(len(closes) * (1 - config.OUT_OF_SAMPLE))]
    btc = closes.iloc[:, 0].pct_change().fillna(0)
    zero = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    out = {"from": f"{closes.index[0]:%d/%m/%Y}", "to": f"{closes.index[-1]:%d/%m/%Y}", "split": f"{split:%d/%m/%Y}",
           "n_assets": closes.shape[1]}
    for label, mask in (("all", closes.index >= closes.index[0]), ("after", closes.index >= split)):
        out[label] = {k: stats(net[mask], w[mask], "1d")[k] for k in ("cagr", "sharpe", "dd")}
        out["btc_" + label] = {k: stats(btc[mask], zero[mask], "1d")[k] for k in ("cagr", "sharpe", "dd")}
    weeks = len(w) / 7
    out["orders_week"] = float((w.diff().abs() > 1e-4).sum().sum() / weeks)
    out["invested"] = float(w.abs().sum(axis=1).mean())
    return out


if __name__ == "__main__":
    closes, w, net = run()
    s = summary()
    print(f"{s['n_assets']} cryptos, {s['from']} -> {s['to']} | « après » depuis le {s['split']}")
    for label, key, ref in (("Toute la période", "all", "btc_all"), ("Après la coupure", "after", "btc_after")):
        a, b = s[key], s[ref]
        print(f"{label:18} stratégie {a['cagr']:+6.1%}/an (Sharpe {a['sharpe']:.2f}, pire baisse {a['dd']:.0%})"
              f"  |  BTC gardé {b['cagr']:+6.1%}/an (Sharpe {b['sharpe']:.2f}, pire baisse {b['dd']:.0%})")
    print(f"Ordres par semaine : {s['orders_week']:.1f} (toutes cryptos confondues) | capital investi en moyenne : {s['invested']:.0%}")
    yearly = (1 + net).groupby(net.index.year).prod() - 1
    print("Par année :", "  ".join(f"{y}: {r:+.0%}" for y, r in yearly.items()))
    invested = w.abs().sum(axis=1)
    by_q = invested.groupby(invested.index.to_period("Q")).mean()
    print("Capital investi par trimestre :", "  ".join(f"{q}: {v:.0%}" for q, v in by_q.items()))
    orders = (w.diff().abs() > 1e-4).sum(axis=1)
    by_q = orders.groupby(orders.index.to_period("Q")).sum() / (orders.groupby(orders.index.to_period("Q")).size() / 7)
    print("Ordres par semaine, par trimestre :", "  ".join(f"{q}: {v:.0f}" for q, v in by_q.items()))
