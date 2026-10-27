"""Compare toutes les stratégies, en 1h et en 4h, sur le panier de cryptos.

L'historique est coupé en deux : « avant » et « après » (les derniers 30 %, vus
comme des données neuves). Une stratégie sérieuse doit tenir sur les deux.

Usage :  python backtest.py              (1h et 4h)
         python backtest.py 4h           (une seule unité de temps)
"""
import sys

import pandas as pd

import config
from data import fetch_history, resample
from engine import hold_stats, net_returns, stats
from strategy import STRATEGIES, weights


def load():
    print("Chargement des prix (le premier lancement télécharge 4 ans de bougies 1h)...")
    return {s: fetch_history(s) for s in config.SYMBOLS}


def run(raw, timeframe):
    bars = {s: resample(df, timeframe) for s, df in raw.items()}
    closes = pd.DataFrame({s: df["close"] for s, df in bars.items()})
    split = closes.index[int(len(closes) * (1 - config.OUT_OF_SAMPLE))]
    print(f"\n=== {timeframe} | {closes.index[0]:%Y-%m-%d} -> {closes.index[-1]:%Y-%m-%d} | "
          f"« après » = depuis le {split:%Y-%m-%d} ===")
    print(f"{'':16} {'Période':7} {'Rdt/an':>8} {'Sharpe':>7} {'Pire DD':>8} {'Trades/an':>10} {'Expo':>5} {'dont short':>10}")
    rows = []
    for name in STRATEGIES:
        w = weights(name, bars, timeframe)
        net = net_returns(w, closes, timeframe)
        for period, mask in (("avant", net.index < split), ("après", net.index >= split)):
            s = stats(net[mask], w[mask], timeframe)
            rows.append({"timeframe": timeframe, "strategy": name, "period": period, **s})
            print(f"{name:16} {period:7} {s['cagr']:>+8.1%} {s['sharpe']:>7.2f} {s['dd']:>8.1%} "
                  f"{s['trades_year']:>10.0f} {s['expo']:>5.0%} {s['short']:>10.0%}")
    for period, mask in (("avant", closes.index < split), ("après", closes.index >= split)):
        for name, s in hold_stats(closes[mask], timeframe).items():
            print(f"{name:16} {period:7} {s['cagr']:>+8.1%} {s['sharpe']:>7.2f} {s['dd']:>8.1%}")
    return rows


if __name__ == "__main__":
    raw = load()
    rows = []
    for tf in sys.argv[1:] or ["1h", "4h"]:
        rows += run(raw, tf)
    pd.DataFrame(rows).to_csv("backtest_result.csv", index=False)
    print(f"\nFrais {config.FEE:.2%} + slippage {config.SLIPPAGE:.2%} par ordre, financement "
          f"{config.FUNDING_PER_DAY:.2%}/jour. Sharpe = rendement / risque (> 1 = bon, < 0,5 = faible). "
          "Pire DD = pire baisse du capital. Expo = part moyenne du capital engagée.")
