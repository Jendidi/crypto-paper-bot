"""Moteur de calcul commun au backtest et au paper trader.

Une stratégie produit des poids par crypto et par bougie : +0,1 = 10 % du capital
acheté, -0,1 = 10 % vendu à découvert, 0 = rien. Le poids décidé à la clôture d'une
bougie est tenu pendant la bougie suivante (en crypto, l'ouverture suivante est
égale à la clôture précédente). Les frais sont payés à chaque changement de poids.
"""
import numpy as np
import pandas as pd

import config
from data import BARS_PER_DAY


def net_returns(weights, closes, timeframe):
    """Rendement net du portefeuille à chaque bougie, frais et financement inclus."""
    held = weights.shift(1).fillna(0)
    rets = closes.pct_change().fillna(0)
    gross = (held * rets).sum(axis=1)
    turnover = held.diff().abs().sum(axis=1).fillna(held.abs().sum(axis=1))
    costs = turnover * (config.FEE + config.SLIPPAGE)
    funding = held.abs().sum(axis=1) * config.FUNDING_PER_DAY / BARS_PER_DAY[timeframe]
    return gross - costs - funding


def stats(net, weights, timeframe):
    bars_year = 365 * BARS_PER_DAY[timeframe]
    eq = (1 + net).cumprod()
    years = len(net) / bars_year
    std = net.std()
    changes = (weights.diff().abs() > 1e-9).sum().sum()
    return {
        "cagr": eq.iloc[-1] ** (1 / years) - 1,
        "sharpe": net.mean() / std * np.sqrt(bars_year) if std else 0.0,
        "dd": (eq / eq.cummax() - 1).min(),
        "trades_year": changes / years,
        "expo": weights.abs().sum(axis=1).mean(),
        "short": weights.clip(upper=0).abs().sum(axis=1).mean(),
    }


def hold_stats(closes, timeframe):
    """Références : garder du BTC, et garder le panier à parts égales."""
    w_btc = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    w_btc[closes.columns[0]] = 1.0
    w_all = closes.notna().astype(float)
    w_all = w_all.div(w_all.sum(axis=1), axis=0)
    out = {}
    for name, w in (("BTC hold", w_btc), ("Panier hold", w_all)):
        r = (w.shift(1).fillna(0) * closes.pct_change().fillna(0)).sum(axis=1)
        out[name] = stats(r, w * 0, timeframe)
    return out
