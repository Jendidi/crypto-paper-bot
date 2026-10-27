"""Télécharge 2 ans de bougies 15 minutes des 25 cryptos dans data/ (données publiques de Binance)."""
import time

import config
from data import fetch_history

start = time.time()
for i, s in enumerate(config.SYMBOLS, 1):
    df = fetch_history(s, days=730, interval="15m")
    print(f"[{i}/{len(config.SYMBOLS)}] {s}: {len(df)} bougies, {df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d} ({time.time() - start:.0f}s)", flush=True)
print("terminé", flush=True)
