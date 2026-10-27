"""Version « 15 minutes » de la stratégie blend : mêmes signaux, suivis à chaque bougie de 15 minutes.

- Volet tendance : inchangé (décision à la clôture du jour, rééquilibrage hebdomadaire).
- Volet retours à la moyenne : le RSI 2, la moyenne 5 jours et la moyenne 200 jours sont recalculés à chaque bougie
  de 15 minutes avec le prix du moment comme « clôture provisoire » du jour. On achète dès que le repli violent se
  produit (au lieu d'attendre minuit), on vend dès le rebond, et le stop (3 ATR sous le prix d'entrée) est contrôlé
  toutes les 15 minutes sur le prix de clôture de chaque bougie. À la dernière bougie du jour, les valeurs provisoires
  deviennent exactement celles de la version journalière.
Le même code sert au backtest et au paper trading.
"""
import numpy as np
import pandas as pd

import config
from strategy import atr, cap_gross, no_trade_band, size_multiplier, tsmom

BARS_DAY = 96


def _prev_day(series, day):
    """Valeur de la dernière journée COMPLÈTE avant chaque bougie : celle de la veille."""
    s = series.copy()
    s.index = s.index + pd.Timedelta(days=1)
    return s.reindex(day, method="ffill").to_numpy(dtype=float)


def rsi2_intraday(closes15, bars1d, thr=5, atr_mult=3.0, risk=0.01, max_hold_days=10, cap=0.25,
                  entry_close_only=False, rebound_close_only=False):
    """entry_close_only : on n'achète qu'à la dernière bougie du jour (comme la version journalière).
    rebound_close_only : on ne vend au rebond qu'à la dernière bougie du jour ; le stop reste contrôlé toutes les 15 min."""
    idx = closes15.index
    day = idx.normalize()
    is_last = ((idx.hour == 23) & (idx.minute == 45))
    out = {}
    for s in closes15.columns:
        d = bars1d[s]
        dc = d["close"]
        delta = dc.diff()
        ag = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
        al = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
        pc, ag_p, al_p = _prev_day(dc, day), _prev_day(ag, day), _prev_day(al, day)
        s4, s199, atr_p = _prev_day(dc.rolling(4).sum(), day), _prev_day(dc.rolling(199).sum(), day), _prev_day(atr(d), day)
        c = closes15[s].to_numpy()
        agt, alt = 0.5 * ag_p + 0.5 * np.maximum(c - pc, 0), 0.5 * al_p + 0.5 * np.maximum(pc - c, 0)
        with np.errstate(divide="ignore", invalid="ignore"):
            rsi = 100 - 100 / (1 + agt / alt)
        rsi = np.where(alt == 0, 100.0, rsi)
        sma5, sma200 = (s4 + c) / 5, (s199 + c) / 200
        w, pos, stop, size, held = np.zeros(len(c)), False, 0.0, 0.0, 0
        limit = max_hold_days * BARS_DAY
        for i in range(len(c)):
            if not pos:
                if c[i] > sma200[i] and rsi[i] < thr and np.isfinite(atr_p[i]) and atr_p[i] > 0 and (is_last[i] or not entry_close_only):
                    pos, stop, held = True, c[i] - atr_mult * atr_p[i], 0
                    size = min(cap, risk / (atr_mult * atr_p[i] / c[i]))
            else:
                held += 1
                if (c[i] > sma5[i] and (is_last[i] or not rebound_close_only)) or c[i] < stop or held >= limit:
                    pos = False
            w[i] = size if pos else 0.0
        out[s] = w
    return pd.DataFrame(out, index=idx)


def trend_intraday(closes15, closes1d):
    """Poids du volet tendance : décidés à la clôture de la veille, nouveaux poids appliqués dès la dernière bougie du jour."""
    idx = closes15.index
    day = idx.normalize()
    wd = tsmom(closes1d, long_only=True)
    prev = wd.copy()
    prev.index = prev.index + pd.Timedelta(days=1)
    arr = prev.reindex(day, method="ffill")[list(closes15.columns)].to_numpy(dtype=float, copy=True)
    last = (idx.hour == 23) & (idx.minute == 45)
    same = wd.reindex(day, method="ffill")[list(closes15.columns)].to_numpy(dtype=float)
    arr[last] = same[last]
    return pd.DataFrame(np.nan_to_num(arr), index=idx, columns=closes15.columns)


def weights15(bars15, bars1d, size=None, band=None, **rsi_options):
    """bars15 : {symbole: OHLCV 15 min}, bars1d : {symbole: OHLCV jour}. Poids du portefeuille par bougie de 15 minutes."""
    closes15 = pd.DataFrame({s: b["close"] for s, b in bars15.items()}).dropna()
    closes1d = pd.DataFrame({s: b["close"] for s, b in bars1d.items()})
    raw = 0.5 * trend_intraday(closes15, closes1d) + rsi2_intraday(closes15, bars1d, **rsi_options)
    w = cap_gross(raw.mul(size_multiplier(closes15.index, size), axis=0))
    return no_trade_band(w, band), closes15
