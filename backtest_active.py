"""Backtest de la stratégie active (active.py) : fréquence, résultats avant/après, par année, sensibilité.

Usage :  python backtest_active.py            (rapport complet)
         python backtest_active.py quick       (résultat principal seulement)
"""
import sys

import numpy as np
import pandas as pd

import active
import config
from data import cached_history


def window_stats(res, lo=None, hi=None):
    eq = res["equity"]
    m = np.ones(len(eq), dtype=bool)
    if lo is not None:
        m &= eq.index >= lo
    if hi is not None:
        m &= eq.index < hi
    eq = eq[m]
    days = (eq.index[-1] - eq.index[0]).days or 1
    daily = eq.resample("1D").last().dropna().pct_change().dropna()
    tr = [t for t in res["trades"] if (lo is None or pd.Timestamp(t["close"]) >= lo) and (hi is None or pd.Timestamp(t["close"]) < hi)]
    pnl = np.array([t["pnl"] for t in tr]) if tr else np.array([0.0])
    wins, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    total = eq.iloc[-1] / eq.iloc[0] - 1
    return {
        "days": days, "ret": total, "cagr": (1 + total) ** (365 / days) - 1 if total > -1 else -1.0,
        "sharpe": daily.mean() / daily.std() * np.sqrt(365) if daily.std() else 0.0,
        "dd": (eq / eq.cummax() - 1).min(), "n": len(tr), "per_week": len(tr) / (days / 7),
        "win": float(np.mean([t["pnl"] > 0 for t in tr])) if tr else 0.0,
        "avg_r": float(np.mean([t["r"] for t in tr])) if tr else 0.0,
        "pf": wins / losses if losses else float("inf"),
        "hours": float(np.mean([t["hours"] for t in tr])) if tr else 0.0,
        "short": float(np.mean([t["side"] < 0 for t in tr])) if tr else 0.0,
    }


def line(label, s):
    return (f"{label:22} {s['cagr']:>+8.1%} {s['sharpe']:>7.2f} {s['dd']:>8.1%} {s['per_week']:>9.1f} {s['n']:>6} "
            f"{s['win']:>6.0%} {s['avg_r']:>+7.2f} {s['pf']:>6.2f} {s['hours']:>7.0f}h {s['short']:>6.0%}")


HEADER = f"{'':22} {'Rdt/an':>8} {'Sharpe':>7} {'Pire DD':>8} {'Trades/s':>9} {'Total':>6} {'Gagn.':>6} {'R moy':>7} {'PF':>6} {'Durée':>8} {'Short':>6}"


def main():
    quick = "quick" in sys.argv
    bars = {s: cached_history(s) for s in config.SYMBOLS}
    prep = active.prepare(bars)
    res = active.simulate(prep)
    idx = prep["index"]
    split = idx[int(prep["t_ready"] + (len(idx) - prep["t_ready"]) * (1 - config.OUT_OF_SAMPLE))]
    print(f"{res['equity'].index[0]:%Y-%m-%d} -> {res['equity'].index[-1]:%Y-%m-%d} | « après » depuis le {split:%Y-%m-%d}")
    print(f"Frais {config.FEE:.2%} (ordres au marché) / {config.MAKER_FEE:.2%} (objectifs) + glissement {config.SLIPPAGE:.2%}, "
          f"financement {config.FUNDING_PER_DAY:.2%}/jour, risque {config.ACTIVE['risk_per_trade']:.0%} par trade\n")
    print(HEADER)
    print(line("Toute la période", window_stats(res)))
    print(line("Avant", window_stats(res, hi=split)))
    print(line("Après", window_stats(res, lo=split)))
    closes = pd.DataFrame({s: b["close"] for s, b in bars.items()}).dropna()
    btc = closes.iloc[:, 0].loc[res["equity"].index[0]:]
    print(f"{'BTC gardé':22} {(btc.iloc[-1] / btc.iloc[0]) ** (365 / (btc.index[-1] - btc.index[0]).days) - 1:>+8.1%}")
    if quick:
        return
    print("\nPar année (rendement, trades/semaine, trades)")
    for y in sorted({t.year for t in res["equity"].index}):
        s = window_stats(res, lo=pd.Timestamp(f"{y}-01-01"), hi=pd.Timestamp(f"{y + 1}-01-01"))
        print(f"  {y}: {s['ret']:>+7.1%}   {s['per_week']:>4.1f}/sem   {s['n']:>4} trades   (DD {s['dd']:.0%})")
    print("\nSorties :", pd.Series([t["reason"] for t in res["trades"]]).value_counts().to_dict())
    by_sym = pd.DataFrame(res["trades"]).groupby("symbol")["pnl"].agg(["count", "sum"]).round(0)
    print("Par crypto (nb, gain total) :", {k: (int(v["count"]), int(v["sum"])) for k, v in by_sym.iterrows()})

    print("\nSensibilité (toute la période)")
    print(HEADER)
    variants = [("score_min=1", dict(score_min=1)), ("score_min=3", dict(score_min=3)),
                ("bear_extra=0", dict(bear_extra=0)), ("bear_extra=2", dict(bear_extra=2)),
                ("risque 0,5 %", dict(risk_per_trade=0.005)), ("risque 2 %", dict(risk_per_trade=0.02)),
                ("sans cooldown", dict(cooldown_bars=0)), ("durée max 72 h", dict(max_hold_bars=72)),
                ("TP 1:1,5 à 1:2", dict(tp_r_min=1.5, tp_r_max=2.0))]
    for label, kw in variants:
        r = active.simulate(prep, params=kw)
        print(line(label, window_stats(r)))


if __name__ == "__main__":
    main()
