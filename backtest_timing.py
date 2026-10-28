"""Les décisions restent celles de la stratégie journalière ; les bougies de 15 minutes servent à choisir le MOMENT d'exécuter.

Quand la stratégie décide d'acheter (ou d'augmenter une position) à la clôture du jour, l'ordre n'est pas forcément passé
tout de suite : le bot attend, pendant 12 ou 24 h au maximum, un moment favorable lu sur les bougies de 15 minutes, puis
passe l'ordre au prix de clôture de cette bougie (ou à la fin de la fenêtre si rien ne se présente). Les ventes restent
immédiates. Le nombre d'ordres est donc le même qu'en version journalière.

Moments testés :
  confirme  : le prix repasse au-dessus de sa moyenne 20 bougies (5 h) avec une bougie verte = la baisse se stabilise.
  creux     : le prix est passé 0,5 % sous le prix de décision = on achète moins cher.
  les deux  : le premier des deux.
Usage :  python backtest_timing.py
"""
import numpy as np
import pandas as pd

import backtest_blend
import config
from data import fetch_history
from engine import net_returns, stats


def prepare(bars15):
    closes = pd.DataFrame({s: b["close"] for s, b in bars15.items()}).dropna()
    idx = closes.index
    return {
        "idx": idx, "closes": closes,
        "o": pd.DataFrame({s: bars15[s]["open"] for s in bars15}).reindex(idx),
        "ema": closes.ewm(span=20, adjust=False).mean(),
        "last": ((idx.hour == 23) & (idx.minute == 45)),
    }


def timed_weights(wd, prep, mode="now", window=96, dip=0.005):
    """wd : poids journaliers décidés à la clôture de chaque jour (colonnes 'BTC', 'ETH'...). Renvoie poids 15 min + statistiques."""
    idx, closes, last = prep["idx"], prep["closes"], prep["last"]
    day = idx.normalize()
    out = pd.DataFrame(0.0, index=idx, columns=closes.columns)
    gains, forced, buys = [], 0, 0
    for s in closes.columns:
        name = s.split("/")[0]
        daily = wd[name].reindex(day).to_numpy(dtype=float)
        c, o, ema = closes[s].to_numpy(), prep["o"][s].to_numpy(), prep["ema"][s].to_numpy()
        prev = wd[name].shift(1).reindex([day[0]]).to_numpy(dtype=float)[0]
        cur = 0.0 if np.isnan(prev) else prev
        pending, ref, start, w = None, 0.0, 0, np.zeros(len(c))
        for i in range(len(c)):
            if last[i]:
                if pending is not None:                              # fin de fenêtre : on exécute au marché
                    gains.append(ref / c[i] - 1); forced += 1; buys += 1
                    cur, pending = pending, None
                tgt = daily[i] if not np.isnan(daily[i]) else cur
                if tgt <= cur + 1e-12 or mode == "now":
                    if tgt > cur + 1e-12:
                        buys += 1; gains.append(0.0)
                    cur = tgt
                else:
                    pending, ref, start = tgt, c[i], i
            elif pending is not None:
                ok = False
                if mode in ("confirme", "les deux"):
                    ok = c[i] > ema[i] and c[i] > o[i]
                if mode in ("creux", "les deux"):
                    ok = ok or c[i] <= ref * (1 - dip)
                if ok:
                    gains.append(ref / c[i] - 1); buys += 1
                    cur, pending = pending, None
                elif i - start >= window:
                    gains.append(ref / c[i] - 1); forced += 1; buys += 1
                    cur, pending = pending, None
            w[i] = cur
        out[s] = w
    return out, {"buys": buys, "forced": forced, "gain": float(np.mean(gains)) if gains else 0.0}


def daily_stats(net, w):
    nd = (1 + net).resample("1D").prod() - 1
    return stats(nd, w.resample("1D").last(), "1d")


def show(label, net, w, split, weeks, extra=""):
    cols = []
    for mask in (np.ones(len(net), bool), net.index < split, net.index >= split):
        s = daily_stats(net[mask], w[mask])
        cols.append(f"{s['cagr']:>+6.1%} Sh{s['sharpe']:>5.2f} DD{s['dd']:>5.0%}")
    orders = (w.diff().abs() > 1e-4).sum().sum() / weeks
    print(f"{label:22} " + " | ".join(f"{c:^22}" for c in cols) + f" | {orders:>4.1f} ordres/sem {extra}")


def main():
    bars15 = {s: fetch_history(s, days=730, interval="15m") for s in config.SYMBOLS}
    prep = prepare(bars15)
    closes_d, wd, netd = backtest_blend.run(2.0)
    split = prep["idx"][int(len(prep["idx"]) * 0.6)]
    weeks = len(prep["idx"]) / (96 * 7)
    print(f"{len(config.SYMBOLS)} cryptos, {prep['idx'][0]:%Y-%m-%d} -> {prep['idx'][-1]:%Y-%m-%d}, coupure {split:%Y-%m-%d}")
    print(f"{'':22} {'tout':^22} | {'avant':^22} | {'après':^22}")
    for mode, window in (("now", 96), ("confirme", 96), ("confirme", 48), ("creux", 96), ("creux", 48), ("les deux", 96), ("les deux", 48)):
        w15, info = timed_weights(wd, prep, mode, window)
        net15 = net_returns(w15, prep["closes"], "15m")
        label = "à minuit (référence)" if mode == "now" else f"{mode}, {window // 4} h max"
        extra = "" if mode == "now" else f"| achetés {info['gain']:+.2%} moins cher, {info['forced'] / max(info['buys'], 1):.0%} forcés en fin de fenêtre"
        show(label, net15, w15, split, weeks, extra)
    m = netd.index >= prep["idx"][0].normalize()
    show("journalier (contrôle)", netd[m], wd[m], split, m.sum() / 7)


if __name__ == "__main__":
    main()
