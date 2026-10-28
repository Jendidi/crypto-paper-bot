"""Prix des cryptos via l'API publique de Binance (données de marché, aucune clé).

On passe d'abord par data-api.binance.vision, le miroir de données de Binance, qui
n'est pas bloqué depuis les États-Unis (là où tournent les serveurs GitHub), puis par
api.binance.com si le miroir ne répond pas.
L'historique 1h est mis en cache dans data/ pour ne pas le retélécharger à chaque backtest.
"""
import json
import time
from pathlib import Path

import pandas as pd
import requests

import config

CACHE = Path("data")
BARS_PER_DAY = {"15m": 96, "1h": 24, "4h": 6, "1d": 1}
HOSTS = ["https://data-api.binance.vision", "https://api.binance.com"]
COLUMNS = ["open", "high", "low", "close", "volume"]
_session = requests.Session()


def _get(path, params):
    """GET avec nouvelles tentatives : l'API coupe parfois la connexion."""
    error = None
    for attempt in range(5):
        for host in HOSTS:
            try:
                r = _session.get(host + path, params=params, timeout=20)
                if r.status_code == 200:
                    return r.json()
                error = RuntimeError(f"{host}{path} : HTTP {r.status_code} {r.text[:120]}")
            except requests.RequestException as e:
                error = e
        time.sleep(2 ** attempt)
    raise error


def _pair(symbol):
    return symbol.replace("/", "")


def _to_df(rows):
    df = pd.DataFrame([r[:6] for r in rows], columns=["ts", *COLUMNS])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    df[COLUMNS] = df[COLUMNS].astype(float)
    return df.drop_duplicates("ts").set_index("ts").sort_index()


def fetch_recent(symbol, timeframe, limit=1000):
    """Dernières bougies, pour le paper trader. La dernière (en cours) est retirée."""
    rows = _get("/api/v3/klines", {"symbol": _pair(symbol), "interval": timeframe, "limit": limit})
    return _to_df(rows).iloc[:-1]


def fetch_since(symbol, interval, since):
    """Toutes les bougies terminées depuis `since` (UTC, sans fuseau). La bougie en cours est retirée."""
    start = int((pd.Timestamp(since) - pd.Timestamp("1970-01-01")) // pd.Timedelta("1ms"))
    rows = []
    while True:
        batch = _get("/api/v3/klines", {"symbol": _pair(symbol), "interval": interval, "startTime": start, "limit": 1000})
        if not batch:
            break
        rows += batch
        start = batch[-1][0] + 1
        if len(batch) < 1000:
            break
    return _to_df(rows).iloc[:-1]


def fetch_prices(symbols):
    """Derniers prix du marché : {symbole: prix}."""
    wanted = json.dumps([_pair(s) for s in symbols], separators=(",", ":"))
    rows = _get("/api/v3/ticker/price", {"symbols": wanted})
    by_pair = {r["symbol"]: float(r["price"]) for r in rows}
    return {s: by_pair[_pair(s)] for s in symbols}


def fetch_history(symbol, days=None, interval="1h"):
    """Historique complet (1h par défaut, ou 15m...), avec cache local mis à jour de façon incrémentale."""
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{symbol.replace('/', '_')}_{interval}.csv"
    old = pd.read_csv(path, index_col="ts", parse_dates=True) if path.exists() else None
    since = (int(old.index[-1].timestamp() * 1000) + 1 if old is not None
             else int((time.time() - (days or config.HISTORY_DAYS) * 86_400) * 1000))
    rows = []
    while True:
        batch = _get("/api/v3/klines", {"symbol": _pair(symbol), "interval": interval, "startTime": since, "limit": 1000})
        if not batch:
            break
        rows += batch
        since = batch[-1][0] + 1
        if len(batch) < 1000:
            break
        time.sleep(0.1)
    parts = [d for d in (old, _to_df(rows) if rows else None) if d is not None]
    df = pd.concat(parts)
    df = df[~df.index.duplicated()].sort_index().iloc[:-1]   # dernière bougie = en cours
    df.to_csv(path)
    return df


def fetch_daily(symbol, days=1600, refresh=False):
    """Bougies journalières (cache data/<symbole>_1d.csv). Utile pour tester de nombreuses cryptos vite."""
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{symbol.replace('/', '_')}_1d.csv"
    if path.exists() and not refresh:
        return pd.read_csv(path, index_col="ts", parse_dates=True)
    since, rows = int((time.time() - days * 86_400) * 1000), []
    while True:
        batch = _get("/api/v3/klines", {"symbol": _pair(symbol), "interval": "1d", "startTime": since, "limit": 1000})
        rows += batch
        if len(batch) < 1000:
            break
        since = batch[-1][0] + 1
    df = _to_df(rows).iloc[:-1]
    df.to_csv(path)
    return df


def cached_history(symbol, refresh=False):
    """Historique 1h lu dans le cache local (data/) ; téléchargé s'il n'existe pas ou si refresh=True."""
    path = CACHE / f"{symbol.replace('/', '_')}_1h.csv"
    if refresh or not path.exists():
        return fetch_history(symbol)
    return pd.read_csv(path, index_col="ts", parse_dates=True)


def resample(df, timeframe):
    if timeframe == "1h":
        return df
    rule = {"4h": "4h", "1d": "1D"}[timeframe]
    return df.resample(rule).agg({"open": "first", "high": "max", "low": "min",
                                  "close": "last", "volume": "sum"}).dropna()
