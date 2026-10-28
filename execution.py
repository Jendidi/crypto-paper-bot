"""Exécution des ordres : décisions journalières, moment choisi sur les bougies de 15 minutes, protections par position.

À la dernière bougie de 15 minutes du jour (23:45 UTC, qui se termine à 00:00), la stratégie journalière donne les positions
cibles. Les ventes sont exécutées tout de suite, au prix de clôture de cette bougie. Un achat (ou une hausse de position) est mis
« en attente » et n'est exécuté qu'au premier bon moment des bougies suivantes, au prix de clôture de la bougie, 24 h au maximum :
  - la baisse se stabilise : le prix repasse au-dessus de sa moyenne sur `ema` bougies avec une bougie verte, ou
  - le prix est passé `dip` sous le prix de décision (on achète moins cher).
Chaque position peut avoir un stop-loss et un take-profit (par rapport au prix d'entrée moyen), contrôlés à CHAQUE bougie de
15 minutes sur le prix de clôture ; une sortie sur stop ou TP est suivie d'un délai avant de racheter la même crypto.
Un budget d'ordres sur 7 jours glissants peut limiter les achats et réductions (les sorties complètes restent permises).
Les frais, le glissement et le financement sont ceux de engine.net_returns, bougie par bougie.
`advance` sert au paper trading ; backtest_exec.py teste les mêmes règles sur 2 ans.
"""
from collections import deque

import numpy as np
import pandas as pd

import config

BARS_PER_DAY = 96
EPS = 1e-3          # écart de position (part du capital) en dessous duquel on ne change rien : absorbe les arrondis
WEEK = pd.Timedelta(days=7)


def advance(state, closes, opens, wd, record=None, trace=None, params=None):
    """Traite les bougies de 15 minutes terminées depuis state['last_bar'] et met l'état à jour.

    closes, opens : bougies 15 min (colonnes = symboles), doivent contenir la bougie state['last_bar'] et assez de bougies avant
                    elle pour la moyenne. wd : positions cibles journalières (index = jour de la bougie, colonnes = symboles),
                    décidées à la clôture de ce jour.
    record(exec_ts, symbole, ancienne_position, nouvelle_position, prix, raison) est appelé à chaque ordre.
    Renvoie le nombre de bougies traitées."""
    p = {**config.EXEC, **(params or {})}
    syms = list(closes.columns)
    idx = closes.index
    t_last = pd.Timestamp(state["last_bar"])
    if t_last not in idx:
        raise ValueError(f"la bougie {t_last} manque dans les données 15 min")
    i0 = idx.get_loc(t_last)
    C = closes.to_numpy(dtype=float)
    O = opens.reindex(idx)[syms].to_numpy(dtype=float)
    EMA = closes.ewm(span=p["ema"], adjust=False).mean().to_numpy(dtype=float)
    hours, minutes, days = idx.hour.to_numpy(), idx.minute.to_numpy(), idx.normalize()
    wdc = wd.reindex(columns=syms)
    wd_days = set(wdc.index)
    wd_arr = wdc.to_numpy(dtype=float)
    wd_row = {d: r for r, d in enumerate(wdc.index)}
    cost, fund = config.FEE + config.SLIPPAGE, config.FUNDING_PER_DAY / BARS_PER_DAY
    sl = np.array([(p["sl_major"] if s in p["majors"] else p["sl_alt"]) or np.nan for s in syms], dtype=float)
    tp = p["tp"]

    cur = np.array([state["weights"].get(s, 0.0) for s in syms], dtype=float)
    prev = np.array([state["prev_weights"].get(s, 0.0) for s in syms], dtype=float)
    entry = np.array([state["entry"].get(s, 0.0) for s in syms], dtype=float)
    cool = np.array([state["cooldown"].get(s, 0) for s in syms], dtype=int)
    pending = state["pending"]
    orders = deque(pd.Timestamp(x) for x in state["orders_ts"])
    last_close = C[i0].copy()
    equity = state["equity"]
    last_done = i0

    def move(k, new_w, price, ts, why):
        old = float(cur[k])
        if new_w > old:                                        # prix d'entrée moyen
            entry[k] = (entry[k] * old + price * (new_w - old)) / new_w if old > 1e-9 and entry[k] > 0 else price
        if new_w <= 1e-9:
            entry[k] = 0.0
        cur[k] = new_w
        orders.append(ts)
        if record:
            record(str(ts), syms[k], old, float(new_w), float(price), why)

    for i in range(i0 + 1, len(idx)):
        t = idx[i]
        is_last = hours[i] == 23 and minutes[i] == 45
        day = days[i]
        decide = is_last and state.get("decided_day") != str(day)
        if decide and day not in wd_days:
            break                                              # le jour n'est pas encore complet : on réessaiera
        c = C[i]
        equity *= 1.0 + float((cur * (c / last_close - 1.0)).sum() - (np.abs(cur - prev) * cost).sum() - (np.abs(cur) * fund).sum())
        prev, last_close = cur.copy(), c
        state["equity"] = equity
        ts = t + pd.Timedelta(minutes=15)                      # un ordre est exécuté à la clôture de la bougie
        while orders and orders[0] <= ts - WEEK:
            orders.popleft()
        cool = np.maximum(cool - 1, 0)
        free = p["budget"] is None or len(orders) < p["budget"]

        for k in np.flatnonzero(cur > 1e-9):                   # protections de chaque position, à chaque bougie
            if entry[k] <= 0:
                continue
            if not np.isnan(sl[k]) and c[k] <= entry[k] * (1.0 - sl[k]):
                move(k, 0.0, c[k], ts, "stop")
                cool[k] = p["cooldown"]
            elif tp is not None and c[k] >= entry[k] * (1.0 + tp):
                move(k, 0.0, c[k], ts, "objectif")
                cool[k] = p["cooldown"]

        if decide:
            for k, s in enumerate(syms):                       # fin de fenêtre : achats encore en attente
                pend = pending.pop(s, None)
                if pend is not None and (p["budget"] is None or len(orders) < p["budget"]):
                    move(k, pend["target"], c[k], ts, "achat")
            free = p["budget"] is None or len(orders) < p["budget"]
            tgt = wd_arr[wd_row[day]]
            tgt = np.where(np.isnan(tgt), 0.0, tgt)
            for k, s in enumerate(syms):
                if tgt[k] == 0.0 and cur[k] > 1e-9:
                    move(k, 0.0, c[k], ts, "vente")            # sortie complète : toujours permise
                elif tgt[k] < cur[k] - EPS and (p["budget"] is None or len(orders) < p["budget"]):
                    move(k, tgt[k], c[k], ts, "réduction")
                elif tgt[k] > cur[k] + EPS and cool[k] == 0:
                    pending[s] = {"target": float(tgt[k]), "ref": float(c[k]), "bars": 0}
            state["decided_day"] = str(day)
        elif not is_last:
            for k, s in enumerate(syms):
                pend = pending.get(s)
                if pend is None:
                    continue
                pend["bars"] += 1
                if cool[k] > 0:
                    pending.pop(s)
                    continue
                if pend["bars"] >= p["window"] and not free:
                    pending.pop(s)                             # le budget d'ordres est épuisé : l'achat est abandonné
                    continue
                stable = c[k] > EMA[i, k] and c[k] > O[i, k]
                cheaper = c[k] <= pend["ref"] * (1.0 - p["dip"])
                if (stable or cheaper or pend["bars"] >= p["window"]) and (p["budget"] is None or len(orders) < p["budget"]):
                    move(k, pending.pop(s)["target"], c[k], ts, "achat")
        if trace is not None:
            trace.append((t, cur.copy(), equity))
        last_done = i

    done = last_done - i0
    if done:
        state["weights"] = {s: float(cur[k]) for k, s in enumerate(syms)}
        state["prev_weights"] = {s: float(prev[k]) for k, s in enumerate(syms)}
        state["entry"] = {s: float(entry[k]) for k, s in enumerate(syms) if entry[k] > 0}
        state["cooldown"] = {s: int(cool[k]) for k, s in enumerate(syms) if cool[k] > 0}
        state["orders_ts"] = [str(x) for x in orders]
        state["last_bar"] = str(idx[last_done])
        state["last_closes"] = {s: float(last_close[k]) for k, s in enumerate(syms)}
    return done
