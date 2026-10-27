"""Stratégie active : long et short sur bougies 1h, tendance lue en 4h.

Règles (voir config.ACTIVE) :
  - Sens du marché (4h) : EMA50 vs EMA200. Tendance haussière : seulement des achats sur repli.
    Tendance baissière : seulement des ventes à découvert sur rebond. Range : on achète le bas
    du canal et on vend le haut.
  - Signal d'entrée (1h), une confirmation = un point : RSI qui ressort d'une zone de survente
    (ou de surachat), rejet d'une zone clé avec une mèche, cassure d'un plus haut/bas récent avec
    un volume élevé, croisement EMA9/EMA21. En tendance, il en faut `score_min` (2 par défaut).
  - Stop-loss derrière le dernier pivot 4h, entre 3 % et 5 % (7 % sur les altcoins) ; sinon pas de trade.
  - 50 % de la position pris à 1:1, stop remonté au prix d'entrée, le reste vers un objectif de 1:2 à 1:3
    calé sur la zone de liquidité (plus haut ou plus bas des 10 derniers jours).
  - Taille : on risque 1 % du capital par trade, frais compris.

Le même code sert au backtest et au paper trading : `simulate` rejoue l'historique bougie par
bougie. Un ordre décidé à la clôture d'une bougie est exécuté à ce prix de clôture, avec frais et
glissement. Si une bougie touche à la fois le stop et un objectif, on suppose que le stop est
touché en premier (hypothèse prudente).
"""
import numpy as np
import pandas as pd

import config

K_PIVOT = 3                 # un pivot 4h = extrême sur 3 bougies de chaque côté
HTF_DELAY = pd.Timedelta(hours=3)   # une bougie 4h n'est connue qu'à la fin de sa dernière heure
WARMUP_BARS = 2400          # 100 jours : le temps que les moyennes 4h se stabilisent


def rsi(close, n=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss)


def atr(df, n=14):
    prev = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _htf(series, idx):
    """Valeurs 4h ramenées sur l'index 1h, sans regarder le futur."""
    s = series.copy()
    s.index = s.index + HTF_DELAY
    return s.reindex(idx, method="ffill")


def prepare(bars):
    """bars : {symbole: DataFrame OHLCV 1h}. Calcule indicateurs et signaux (vectorisé)."""
    p = config.ACTIVE
    idx = None
    for df in bars.values():
        idx = df.index if idx is None else idx.intersection(df.index)
    idx = idx.sort_values()
    out = {"index": idx, "sym": {}}
    ready_all = np.ones(len(idx), dtype=bool)
    for s, df in bars.items():
        d = df.loc[idx]
        c, o, h, l = d["close"], d["open"], d["high"], d["low"]
        r, a1 = rsi(c), atr(d)
        e9, e21 = c.ewm(span=9, adjust=False).mean(), c.ewm(span=21, adjust=False).mean()
        volr = d["volume"] / d["volume"].rolling(24).mean().shift(1)
        hh48, ll48 = h.rolling(48).max().shift(1), l.rolling(48).min().shift(1)
        hi100, lo100 = h.rolling(100).max().shift(1), l.rolling(100).min().shift(1)
        hh240, ll240 = h.rolling(240).max().shift(1), l.rolling(240).min().shift(1)

        h4 = d.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
        e50, e200, a4 = h4["close"].ewm(span=50, adjust=False).mean(), h4["close"].ewm(span=200, adjust=False).mean(), atr(h4)
        pl = h4["low"].where(h4["low"] == h4["low"].rolling(2 * K_PIVOT + 1, center=True).min()).shift(K_PIVOT).ffill()
        ph = h4["high"].where(h4["high"] == h4["high"].rolling(2 * K_PIVOT + 1, center=True).max()).shift(K_PIVOT).ffill()
        rng_hi, rng_lo = h4["high"].rolling(50).max(), h4["low"].rolling(50).min()
        gap = e50 / e200 - 1
        reg = pd.Series(np.select([(gap > p["regime_gap"]) & (h4["close"] > e200), (gap < -p["regime_gap"]) & (h4["close"] < e200),
                                   gap.abs() < p["regime_gap"]], [1, -1, 0], 2), index=h4.index).astype(float)
        e50, e200, a4, pl, ph, rng_hi, rng_lo, reg = (_htf(x, idx) for x in (e50, e200, a4, pl, ph, rng_hi, rng_lo, reg))

        rng = (h - l).replace(0, np.nan)
        lw, uw = (np.minimum(o, c) - l) / rng, (h - np.maximum(o, c)) / rng
        pos_in = (c - l) / rng
        near_l = pd.Series(False, index=idx)
        near_s = pd.Series(False, index=idx)
        for z in (e50, e200, pl, lo100):
            near_l |= (l <= z + 0.25 * a1) & (c > z) & (l >= z - 1.5 * a1)
        for z in (e50, e200, ph, hi100):
            near_s |= (h >= z - 0.25 * a1) & (c < z) & (h <= z + 1.5 * a1)
        A_l, A_s = (r.shift(1) < 40) & (r >= 40), (r.shift(1) > 60) & (r <= 60)
        B_l, B_s = (lw >= 0.5) & (pos_in >= 0.5) & near_l, (uw >= 0.5) & (pos_in <= 0.5) & near_s
        C_l, C_s = (c > hh48) & (volr >= 1.5), (c < ll48) & (volr >= 1.5)
        D_l, D_s = (e9.shift(1) <= e21.shift(1)) & (e9 > e21), (e9.shift(1) >= e21.shift(1)) & (e9 < e21)

        width = (rng_hi - rng_lo) / c
        edge_lo = (c <= rng_lo + 0.25 * (rng_hi - rng_lo)) & (width > 0.08)
        edge_hi = (c >= rng_hi - 0.25 * (rng_hi - rng_lo)) & (width > 0.08)
        up, down, flat = reg == 1, reg == -1, reg == 0
        ls = np.where(up, A_l.astype(int) + B_l + C_l + D_l, np.where(flat & edge_lo, A_l.astype(int) + B_l, 0))
        ss = np.where(down, A_s.astype(int) + B_s + C_s + D_s, np.where(flat & edge_hi, A_s.astype(int) + B_s, 0))

        dc = c.resample("1D").last()
        dscore = sum(np.sign(dc / dc.shift(L) - 1) for L in (20, 50, 100, 200))
        dscore = dscore.copy()
        dscore.index = dscore.index + pd.Timedelta(hours=23)          # la journée n'est connue qu'à sa dernière heure
        dscore = dscore.reindex(idx, method="ffill")

        ready = np.isfinite(np.column_stack([r, a1, a4, e200, pl, ph, rng_hi, rng_lo, hh240, ll240, hh48, ll48, volr, reg])).all(axis=1)
        ready_all &= ready
        out["sym"][s] = {k: v.to_numpy(dtype=float).tolist() if hasattr(v, "to_numpy") else np.asarray(v, dtype=float).tolist() for k, v in {
            "o": o, "h": h, "l": l, "c": c, "atr": a1, "pl": pl, "ph": ph, "hh240": hh240, "ll240": ll240,
            "rng_hi": rng_hi, "rng_lo": rng_lo, "ls": ls, "ss": ss, "ltr": up.astype(float), "str": down.astype(float),
            "reg": reg, "dscore": dscore.fillna(0), **{f"{side}_{k}": comp.astype(float) for side, comps in (("l", (A_l, B_l, C_l, D_l)), ("s", (A_s, B_s, C_s, D_s)))
                           for k, comp in zip("ABCD", comps)}}.items()}
        out["sym"][s]["ready"] = ready.tolist()
    first = int(np.argmax(ready_all)) if ready_all.any() else len(idx)
    out["t_ready"] = first + WARMUP_BARS
    return out


def simulate(prep, start=None, params=None, start_equity=None):
    """Rejoue la stratégie. Renvoie {equity: Series, events, trades, open, bars}."""
    p = {**config.ACTIVE, **(params or {})}
    idx, S, arr = prep["index"], list(prep["sym"]), prep["sym"]
    N = len(idx)
    t0 = prep["t_ready"]
    if start is not None:
        t0 = max(int(idx.searchsorted(pd.Timestamp(start))), prep.get("t_min", 0))
    start_eq = start_equity or config.STARTING_CASH
    slip, taker, maker = config.SLIPPAGE, config.FEE, config.MAKER_FEE
    fund_bar = config.FUNDING_PER_DAY / 24
    btc_reg = arr[S[0]]["reg"]

    st = {"realized": 0.0}
    pos, cool, events, trades, eq_curve = {}, {s: 0 for s in S}, [], [], []

    def ev(t, s, typ, side, price, qty, reason="", eq=None):
        events.append({"ts": str(idx[t]), "symbol": s, "type": typ, "side": side, "price": price,
                       "qty": qty, "usd": qty * price, "reason": reason})

    def close(t, s, ps, qty, price, rate, reason, final):
        gross = ps["side"] * qty * (price - ps["entry"])
        pnl = gross - rate * qty * price
        st["realized"] += pnl
        ps["pnl"] += pnl
        ps["exit_val"] += qty * price
        ps["exit_qty"] += qty
        ps["qty"] -= qty
        ev(t, s, "close" if final else "tp1", ps["side"], price, qty, reason)
        if final:
            trades.append({"symbol": s, "side": ps["side"], "open": str(idx[ps["t"]]), "close": str(idx[t]),
                           "entry": ps["entry"], "exit": ps["exit_val"] / ps["exit_qty"], "pnl": ps["pnl"],
                           "r": ps["pnl"] / ps["risk"], "reason": reason, "hours": t - ps["t"], "d": ps["d"]})
            del pos[s]
            if reason == "stop":
                cool[s] = t + p["cooldown_bars"]

    for t in range(t0, N):
        for s in list(pos):
            a, ps = arr[s], pos[s]
            o, h, l, c = a["o"][t], a["h"][t], a["l"][t], a["c"][t]
            side = ps["side"]
            fund = ps["qty"] * c * fund_bar
            st["realized"] -= fund
            ps["pnl"] -= fund
            adverse, favour = (l, h) if side > 0 else (h, l)
            if (adverse <= ps["sl"]) if side > 0 else (adverse >= ps["sl"]):
                raw = min(o, ps["sl"]) if side > 0 else max(o, ps["sl"])
                close(t, s, ps, ps["qty"], raw * (1 - side * slip), taker, "breakeven" if ps["tp1"] else "stop", True)
                continue
            hit = lambda lvl: (favour >= lvl) if side > 0 else (favour <= lvl)
            if not ps["tp1"] and hit(ps["tp1p"]):
                fill = max(o, ps["tp1p"]) if side > 0 else min(o, ps["tp1p"])
                close(t, s, ps, ps["qty0"] / 2, fill, maker, "tp1", False)
                ps["tp1"], ps["sl"] = True, ps["entry"]
                if (l <= ps["entry"]) if side > 0 else (h >= ps["entry"]):     # retour sur le breakeven dans la même bougie
                    close(t, s, ps, ps["qty"], ps["entry"] * (1 - side * slip), taker, "breakeven", True)
                    continue
            if ps["tp1"] and hit(ps["tp2p"]):
                fill = max(o, ps["tp2p"]) if side > 0 else min(o, ps["tp2p"])
                close(t, s, ps, ps["qty"], fill, maker, "tp2", True)
                continue
            if t - ps["t"] >= p["max_hold_bars"]:
                close(t, s, ps, ps["qty"], c * (1 - side * slip), taker, "time", True)

        unreal = sum(ps["side"] * ps["qty"] * (arr[s]["c"][t] - ps["entry"]) for s, ps in pos.items())
        eq = start_eq + st["realized"] + unreal
        eq_curve.append(eq)

        bear = btc_reg[t] == -1
        extra = p["bear_extra"] if bear else 0
        room_n = (p["max_concurrent_bear"] if bear else p["max_concurrent"]) - len(pos)
        room_r = p["max_open_risk_trades"] - sum(1 for ps in pos.values() if not ps["tp1"])
        cands = []
        for s in S:
            a = arr[s]
            if s in pos or t < cool[s] or not a["ready"][t]:
                continue
            lreq = p["score_min"] if a["ltr"][t] else 1        # en tendance : plusieurs confirmations ; en range : l'emplacement suffit
            sreq = p["score_min"] if a["str"][t] else 1
            if not p["allow_range"]:
                if not a["ltr"][t]:
                    lreq = 99
                if not a["str"][t]:
                    sreq = 99
            if not p["allow_short"]:
                sreq = 99
            if p["daily_filter"]:
                if a["dscore"][t] < p["dscore_min"]:
                    lreq = 99
                if a["dscore"][t] > -p["dscore_min"]:
                    sreq = 99
            if a["ls"][t] > 0 and a["ls"][t] >= lreq + extra:
                cands.append((lreq - a["ls"][t], 1, s))
            elif a["ss"][t] > 0 and a["ss"][t] >= sreq + extra:
                cands.append((sreq - a["ss"][t], -1, s))
        for _, side, s in sorted(cands):
            if room_n <= 0 or room_r <= 0:
                break
            a = arr[s]
            c, atr1 = a["c"][t], a["atr"][t]
            entry = c * (1 + side * slip)
            if side > 0:
                piv = a["pl"][t]
                base = piv if piv < entry * 0.995 else min(a["l"][t], min(a["l"][max(0, t - 48):t + 1]))
                sl = base - 0.2 * atr1
                d = (entry - sl) / entry
                liq = max(a["rng_hi"][t] if arr[s]["reg"][t] == 0 else a["hh240"][t], entry) / entry - 1
            else:
                piv = a["ph"][t]
                base = piv if piv > entry * 1.005 else max(a["h"][t], max(a["h"][max(0, t - 48):t + 1]))
                sl = base + 0.2 * atr1
                d = (sl - entry) / entry
                liq = 1 - min(a["rng_lo"][t] if arr[s]["reg"][t] == 0 else a["ll240"][t], entry) / entry
            cap = p["sl_cap_major"] if s in p["majors"] else p["sl_cap_alt"]
            d = max(d, p["sl_min"])
            if d > cap:
                continue
            sl = entry * (1 - side * d)
            tp_d = min(max(liq, p["tp_r_min"] * d), p["tp_r_max"] * d, p["tp_cap"])
            risk_amt = p["risk_per_trade"] * eq
            notional = risk_amt / (d + 2 * (taker + slip))
            gross = sum(ps["qty"] * arr[x]["c"][t] for x, ps in pos.items())
            notional = min(notional, p["max_gross"] * eq - gross)
            if notional < 0.1 * risk_amt / d:                      # moins de 10 % de la taille prévue : on passe
                continue
            qty = notional / entry
            fee = taker * qty * entry
            st["realized"] -= fee
            pos[s] = {"side": side, "entry": entry, "sl": sl, "tp1p": entry * (1 + side * p["tp1_r"] * d),
                      "tp2p": entry * (1 + side * tp_d), "qty": qty, "qty0": qty, "tp1": False, "t": t,
                      "pnl": -fee, "exit_val": 0.0, "exit_qty": 0.0, "risk": risk_amt, "d": d, "sl0": sl}
            ev(t, s, "open", side, entry, qty, f"SL {d:.1%} / TP {tp_d:.1%}")
            room_n -= 1
            room_r -= 1

    eq_series = pd.Series(eq_curve, index=idx[t0:t0 + len(eq_curve)])
    open_pos = [{"symbol": s, "side": ps["side"], "entry": ps["entry"], "sl": ps["sl"], "sl0": ps["sl0"], "tp1": ps["tp1p"],
                 "tp2": ps["tp2p"], "qty": ps["qty"], "tp1_done": ps["tp1"], "since": str(idx[ps["t"]]), "risk": ps["risk"]}
                for s, ps in pos.items()]
    return {"equity": eq_series, "events": events, "trades": trades, "open": open_pos, "bars": N - t0}
