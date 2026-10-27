"""Recherche : améliorer le suivi de tendance journalier (plus de cryptos, second signal), avant / après la coupure.

Les cryptos ajoutées sont celles qui existent aujourd'hui avec assez d'historique : l'échantillon est donc
un peu flatteur (biais du survivant), pour toutes les variantes de la même façon.
"""
import numpy as np
import pandas as pd

import config
from data import fetch_daily
from engine import net_returns, stats
from strategy import mean_reversion, tsmom

EXTRA = ["DOT", "ATOM", "UNI", "NEAR", "TRX", "ETC", "XLM", "BCH", "FIL", "AAVE", "ALGO", "VET", "INJ", "OP", "APT"]
BASE = [s.split("/")[0] for s in config.SYMBOLS]


def load(names):
    out = {}
    for n in names:
        try:
            out[n] = fetch_daily(f"{n}/USDT")
        except Exception as e:                                  # paire absente ou trop récente
            print(f"  (ignorée : {n} — {str(e)[:60]})")
    return out


def rsi2_long(bars, n_ref):
    """Retour à la moyenne journalier, achat seul : RSI(2) < 10 dans une tendance haussière (> moyenne 200 j)."""
    pos = pd.DataFrame({s: mean_reversion(df).clip(lower=0) for s, df in bars.items()})
    active = pos.sum(axis=1).clip(lower=1)
    return pos.div(np.maximum(active, n_ref / 3), axis=0)


def block(label, net, w, split):
    cols = []
    for part, mask in (("tout", slice(None)), ("avant", net.index < split), ("après", net.index >= split)):
        s = stats(net[mask], w[mask], "1d")
        cols.append(f"{part} {s['cagr']:>+6.1%} Sh {s['sharpe']:>5.2f} DD {s['dd']:>5.0%}")
    ch = (w.diff().abs() > 1e-4).sum(axis=1)
    print(f"{label:34} " + " | ".join(cols) + f" | {ch.sum() / (len(w) / 7):>4.1f} ordres/sem")


def main():
    bars = load(BASE + EXTRA)
    for tag, names in (("10 cryptos", BASE), ("25 cryptos", list(bars))):
        sub = {n: bars[n] for n in names if n in bars}
        closes = pd.DataFrame({n: d["close"] for n, d in sub.items()})
        closes = closes.loc[closes.index >= "2022-10-27"]
        sub = {n: d.loc[closes.index[0]:] for n, d in sub.items()}
        split = closes.index[int(len(closes) * 0.7)]
        print(f"\n=== {tag} : {closes.index[0]:%Y-%m-%d} -> {closes.index[-1]:%Y-%m-%d} | coupure {split:%Y-%m-%d} ===")
        w1 = tsmom(closes, long_only=True)
        n1 = net_returns(w1, closes, "1d")
        block("tsmom long seul", n1, w1, split)
        w2 = rsi2_long(sub, len(sub)).reindex(closes.index).fillna(0)
        n2 = net_returns(w2, closes, "1d")
        block("RSI2 retour à la moyenne (achat)", n2, w2, split)
        for a in (0.5, 0.7):
            w = a * w1 + (1 - a) * w2
            block(f"mix {a:.0%} tendance / {1 - a:.0%} RSI2", net_returns(w, closes, "1d"), w, split)
        btc = closes.iloc[:, 0]
        hold = btc.pct_change().fillna(0)
        block("BTC gardé", hold, pd.DataFrame(0.0, index=closes.index, columns=closes.columns), split)


if __name__ == "__main__":
    main()
