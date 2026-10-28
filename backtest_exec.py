"""Backtest 2 ans de l'exécution complète (execution.advance) : moment choisi sur 15 min, stop/TP par position, budget d'ordres.

Usage :  python backtest_exec.py
"""
import numpy as np
import pandas as pd

import backtest_blend
import config
import execution
from data import fetch_history


def simulate(prep, wd, params=None, warm=300):
    """Rejoue toute la période et renvoie (courbe d'equity en base 1, liste d'ordres)."""
    closes, opens = prep
    state = {"last_bar": str(closes.index[warm]), "weights": {}, "prev_weights": {}, "entry": {}, "cooldown": {}, "pending": {},
             "orders_ts": [], "equity": 1.0, "decided_day": None, "last_closes": {}}
    trades, trace = [], []
    execution.advance(state, closes, opens, wd, record=lambda ts, s, o, n, px, why: trades.append((ts, s, o, n, px, why)),
                      trace=trace, params=params)
    eq = pd.Series([e for _, _, e in trace], index=[t for t, _, _ in trace])
    return eq, trades, state


def stats(eq, trades, weeks):
    nd = eq.resample("1D").last().pct_change().dropna()
    years = (eq.index[-1] - eq.index[0]).days / 365
    dd = (eq / eq.cummax() - 1).min()
    why = pd.Series([t[5] for t in trades]).value_counts().to_dict()
    return {"cagr": eq.iloc[-1] ** (1 / years) - 1, "sharpe": nd.mean() / nd.std() * np.sqrt(365), "dd": dd,
            "orders": len(trades) / weeks, "why": why}


def line(label, s):
    extra = " ".join(f"{k} {v}" for k, v in s["why"].items() if k in ("stop", "objectif"))
    return f"{label:34} {s['cagr']:>+7.1%} Sh{s['sharpe']:>5.2f} DD{s['dd']:>5.0%} | {s['orders']:>5.1f} ordres/sem | {extra}"


def main():
    bars15 = {s: fetch_history(s, days=730, interval="15m") for s in config.SYMBOLS}
    closes = pd.DataFrame({s: b["close"] for s, b in bars15.items()}).dropna()
    opens = pd.DataFrame({s: bars15[s]["open"] for s in bars15}).reindex(closes.index)
    _, wd, _ = backtest_blend.run(2.0)
    wd.columns = [f"{c}/USDT" for c in wd.columns]
    weeks = (len(closes) - 300) / (96 * 7)
    print(f"{closes.index[300]:%Y-%m-%d} -> {closes.index[-1]:%Y-%m-%d} | x2, bande 2 %, exécution choisie sur 15 min")
    cases = [
        ("référence (sans stop, sans TP)", {}),
        ("budget 14 ordres / 7 jours", dict(budget=14)),
        ("budget 12 ordres / 7 jours", dict(budget=12)),
        ("budget 10 ordres / 7 jours", dict(budget=10)),
        ("stop 25/30 % + budget 12", dict(sl_major=0.25, sl_alt=0.30, budget=12)),
        ("stop 25/30 % + budget 10", dict(sl_major=0.25, sl_alt=0.30, budget=10)),
    ]
    for label, params in cases:
        eq, trades, _ = simulate((closes, opens), wd, params)
        print(line(label, stats(eq, trades, weeks)))


if __name__ == "__main__":
    main()
