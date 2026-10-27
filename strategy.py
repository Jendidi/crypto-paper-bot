"""Stratégies de trading actif, à l'achat ET à la vente à découvert.

Les stratégies « par crypto » renvoient une position par bougie :
+1 = acheteur, -1 = vendeur à découvert, 0 = rien. Chaque crypto reçoit une part
égale du capital (1/10). La stratégie « cross-sectionnelle » compare les cryptos
entre elles et renvoie directement les poids du portefeuille.

Les paramètres sont des valeurs classiques, volontairement non optimisées sur nos
données pour éviter le sur-ajustement.
"""
import numpy as np
import pandas as pd

from data import BARS_PER_DAY


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(close, period):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss)


def atr(df, period=14):
    prev = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def trend_ema(df):
    """Suivi de tendance permanent : acheteur quand l'EMA 50 est au-dessus de
    l'EMA 200, vendeur à découvert sinon. La référence la plus simple."""
    pos = np.where(ema(df["close"], 50) > ema(df["close"], 200), 1, -1)
    pos[:200] = 0
    return pd.Series(pos, index=df.index)


def donchian(df):
    """Cassure de canal (type « Turtle ») dans les deux sens : achète la cassure du
    plus haut sur 55 bougies, vend à découvert la cassure du plus bas. Sortie sur la
    cassure inverse à 20 bougies ou par un stop suiveur à 3 ATR (volatilité)."""
    c = df["close"].to_numpy()
    hi55 = df["high"].rolling(55).max().shift().to_numpy()
    lo55 = df["low"].rolling(55).min().shift().to_numpy()
    hi20 = df["high"].rolling(20).max().shift().to_numpy()
    lo20 = df["low"].rolling(20).min().shift().to_numpy()
    a = atr(df).to_numpy()
    pos = np.zeros(len(c))
    p, extreme = 0, 0.0
    for i in range(len(c)):
        if p == 0:
            if c[i] > hi55[i]:
                p, extreme = 1, c[i]
            elif c[i] < lo55[i]:
                p, extreme = -1, c[i]
        elif p == 1:
            extreme = max(extreme, c[i])
            if c[i] < lo20[i] or c[i] < extreme - 3 * a[i]:
                p = 0
        else:
            extreme = min(extreme, c[i])
            if c[i] > hi20[i] or c[i] > extreme + 3 * a[i]:
                p = 0
        pos[i] = p
    return pd.Series(pos, index=df.index)


def mean_reversion(df):
    """Retour à la moyenne dans le sens de la tendance : en tendance haussière
    (> moyenne 200), achète les excès de baisse (RSI 2 < 10) ; en tendance baissière,
    vend à découvert les excès de hausse (RSI 2 > 90). Sortie au retour vers la
    moyenne 5, ou par un stop de sécurité à 3 ATR. Trades de quelques heures à jours."""
    c = df["close"].to_numpy()
    sma200 = df["close"].rolling(200).mean().to_numpy()
    sma5 = df["close"].rolling(5).mean().to_numpy()
    r = rsi(df["close"], 2).to_numpy()
    a = atr(df).to_numpy()
    pos = np.zeros(len(c))
    p, entry = 0, 0.0
    for i in range(len(c)):
        if p == 0:
            if c[i] > sma200[i] and r[i] < 10:
                p, entry = 1, c[i]
            elif c[i] < sma200[i] and r[i] > 90:
                p, entry = -1, c[i]
        elif p == 1 and (c[i] > sma5[i] or c[i] < entry - 3 * a[i]):
            p = 0
        elif p == -1 and (c[i] < sma5[i] or c[i] > entry + 3 * a[i]):
            p = 0
        pos[i] = p
    return pd.Series(pos, index=df.index)


def xs_momentum(closes, timeframe, lookback_days=30, n=3):
    """Momentum relatif, neutre au marché : chaque lundi à 0h UTC, achète les 3 cryptos
    qui ont le plus monté sur 30 jours et vend à découvert les 3 qui ont le plus baissé.
    Gagne si les gagnantes continuent de surperformer les perdantes, que le marché
    monte ou baisse."""
    bpd = BARS_PER_DAY[timeframe]
    perf = closes / closes.shift(lookback_days * bpd) - 1
    w = pd.DataFrame(np.nan, index=closes.index, columns=closes.columns)
    monday = (closes.index.dayofweek == 0) & (closes.index.hour == 0)
    for i in np.flatnonzero(monday):
        if i < lookback_days * bpd:
            continue
        p = perf.iloc[i].dropna()
        if len(p) < 2 * n:
            continue
        ranked = p.sort_values()
        row = pd.Series(0.0, index=closes.columns)
        row[ranked.index[-n:]] = 0.5 / n          # moitié du capital à l'achat
        row[ranked.index[:n]] = -0.5 / n          # moitié à la vente à découvert
        w.iloc[i] = row
    return w.ffill().fillna(0.0)


def tsmom(closes, lookbacks=(20, 50, 100, 200), long_only=False, vol_target=0.6,
          rebalance_weekday=0, vol_window=30):
    """Momentum de série temporelle (bougies JOURNALIÈRES uniquement), le suivi de tendance
    publié et testé sur des décennies de marchés.

    Pour chaque crypto, on regarde si le prix est plus haut ou plus bas qu'il y a 20, 50,
    100 et 200 jours. Le signal est la moyenne des 4 verdicts, de -1 à +1 : il change
    progressivement. La taille de la position est inversement proportionnelle à la
    volatilité de la crypto (cible 60 % annualisé), le total ne dépasse jamais 100 % du
    capital, et le portefeuille n'est rééquilibré qu'un jour par semaine (lundi) pour
    limiter les frais. En `long_only`, un signal négatif donne simplement zéro position.
    """
    sig = sum(np.sign(closes / closes.shift(L) - 1) for L in lookbacks) / len(lookbacks)
    if long_only:
        sig = sig.clip(lower=0)
    vol = closes.pct_change().rolling(vol_window).std() * np.sqrt(365)
    w = sig * (vol_target / vol).clip(upper=1.0) / closes.shape[1]
    w.loc[w.index.dayofweek != rebalance_weekday] = np.nan   # on ne bouge que le jour de rééquilibrage
    return w.ffill().fillna(0.0)


PER_ASSET = {"trend_ema": trend_ema, "donchian": donchian, "mean_reversion": mean_reversion}
DAILY_ONLY = {"tsmom_lo", "tsmom_ls"}
STRATEGIES = [*PER_ASSET, "xs_momentum", *DAILY_ONLY]


def weights(name, bars, timeframe):
    """`bars` : {symbole: DataFrame OHLCV}. Renvoie les poids du portefeuille (bougies x cryptos)."""
    closes = pd.DataFrame({s: df["close"] for s, df in bars.items()})
    if name in DAILY_ONLY:
        if timeframe != "1d":
            raise ValueError(f"{name} ne fonctionne qu'en bougies journalières (TIMEFRAME = '1d')")
        return tsmom(closes, long_only=(name == "tsmom_lo"))
    if name == "xs_momentum":
        return xs_momentum(closes, timeframe)
    pos = pd.DataFrame({s: PER_ASSET[name](df) for s, df in bars.items()}).reindex(closes.index).fillna(0)
    return pos / len(bars)
