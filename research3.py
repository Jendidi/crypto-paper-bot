"""Mélange tendance (tsmom) + retours à la moyenne dimensionnés au risque (1 %), robustesse aux réglages."""
import numpy as np
import pandas as pd

from engine import net_returns, stats
from research2 import BASE, EXTRA, load
from strategy import atr, rsi, tsmom


def rsi2_sleeve(bars, thr=10, exit_sma=5, atr_mult=3.0, risk=0.01, max_hold=10, cap=0.25):
    """Achat d'un repli violent (RSI 2 < thr) dans une tendance haussière (> moyenne 200 j).
    Sortie au rebond (clôture > moyenne `exit_sma`), au stop (clôture sous entrée - atr_mult x ATR) ou après
    `max_hold` jours. Taille : on perd `risk` du capital si le stop est touché (plafonné à `cap`)."""
    out = {}
    for s, df in bars.items():
        c = df["close"]
        r2, sma200, sma_x, a = rsi(c, 2).to_numpy(), c.rolling(200).mean().to_numpy(), c.rolling(exit_sma).mean().to_numpy(), atr(df).to_numpy()
        cv = c.to_numpy()
        w, pos, stop, size, held = np.zeros(len(c)), False, 0.0, 0.0, 0
        for i in range(len(c)):
            if not pos:
                if cv[i] > sma200[i] and r2[i] < thr and np.isfinite(a[i]):
                    pos, stop, held = True, cv[i] - atr_mult * a[i], 0
                    size = min(cap, risk / (atr_mult * a[i] / cv[i]))
            else:
                held += 1
                if cv[i] > sma_x[i] or cv[i] < stop or held >= max_hold:
                    pos = False
            w[i] = size if pos else 0.0
        out[s] = w
    return pd.DataFrame(out, index=next(iter(bars.values())).index)


def cap_gross(w):
    g = w.abs().sum(axis=1)
    return w.div(np.maximum(g, 1.0), axis=0)


def row(label, w, closes, split):
    net = net_returns(w, closes, "1d")
    cols = []
    for part, mask in (("tout", slice(None)), ("avant", net.index < split), ("après", net.index >= split)):
        s = stats(net[mask], w[mask], "1d")
        cols.append(f"{s['cagr']:>+6.1%} Sh{s['sharpe']:>5.2f} DD{s['dd']:>5.0%}")
    entries = ((w.shift(1).fillna(0) == 0) & (w > 0)).sum().sum()
    print(f"{label:30} " + " | ".join(cols) + f" | {entries / (len(w) / 7):>4.1f} entrées RSI2/sem")


def main():
    bars = load(BASE + EXTRA)
    closes = pd.DataFrame({n: d["close"] for n, d in bars.items()})
    closes = closes.loc[closes.index >= "2022-10-27"]
    bars = {n: d.loc[closes.index[0]:] for n, d in bars.items()}
    split = closes.index[int(len(closes) * 0.7)]
    print(f"{len(bars)} cryptos, {closes.index[0]:%Y-%m-%d} -> {closes.index[-1]:%Y-%m-%d}, coupure {split:%Y-%m-%d}")
    print(f"{'':30} {'tout':^22} | {'avant':^22} | {'après':^22}")
    wt = tsmom(closes, long_only=True)
    row("tendance seule (tsmom_lo)", wt, closes, split)
    for thr, ex in ((10, 5), (5, 5), (15, 5), (10, 10), (5, 10), (15, 10)):
        w2 = rsi2_sleeve(bars, thr=thr, exit_sma=ex).reindex(closes.index)
        row(f"RSI2 seul <{thr} sortie SMA{ex}", w2, closes, split)
        row(f"  mix 0,5 tendance + RSI2", cap_gross(0.5 * wt + w2), closes, split)
    print("\nMultiple d'ATR du stop (RSI2 < 10, sortie SMA5), mix 0,5 tendance + RSI2 :")
    for m in (2.0, 3.0, 4.0):
        w2 = rsi2_sleeve(bars, atr_mult=m)
        row(f"  stop {m:.0f} ATR", cap_gross(0.5 * wt + w2), closes, split)
    print("\nPart de la tendance dans le mix :")
    w2 = rsi2_sleeve(bars)
    for a in (0.3, 0.5, 0.7, 1.0):
        row(f"  {a:.0%} tendance + RSI2", cap_gross(a * wt + w2), closes, split)


if __name__ == "__main__":
    main()
