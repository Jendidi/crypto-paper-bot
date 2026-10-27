"""Génère dashboard.html et docs/index.html : l'état du bot (equity, positions, ordres, graphiques).

Lit paper_state.json et paper_equity.csv écrits par paper_trader.py, ajoute les cours
récents des cryptos, puis remplit dashboard_template.html. Servie par GitHub Pages, la
page rafraîchit en plus les prix en direct dans le navigateur.

Usage :  python dashboard.py
"""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import config
from data import fetch_recent
from engine import hold_stats, net_returns, stats
from research import daily_closes
from strategy import tsmom

HERE = Path(__file__).parent
LOOKBACKS = (20, 50, 100, 200)
SPARK_DAYS = 180


def clean(x):
    """JSON strict : pas de NaN."""
    if isinstance(x, float):
        return None if math.isnan(x) or math.isinf(x) else x
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    return x


def recent_daily(symbol):
    return fetch_recent(symbol, "1d", limit=400)["close"]


def backtest_summary():
    """Résultats du test sur le passé, figés dans backtest_summary.json (supprimez-le pour les recalculer
    à partir du cache local data/, créé par backtest.py)."""
    path = HERE / "backtest_summary.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    out = compute_backtest()
    path.write_text(json.dumps(clean(out), ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def compute_backtest():
    closes = daily_closes().dropna()
    w = tsmom(closes, long_only=True)
    net = net_returns(w, closes, "1d")
    split = closes.index[int(len(closes) * (1 - config.OUT_OF_SAMPLE))]
    out = {"from": f"{closes.index[0]:%d/%m/%Y}", "to": f"{closes.index[-1]:%d/%m/%Y}", "split": f"{split:%d/%m/%Y}"}
    hold = hold_stats(closes, "1d")
    hold_after = hold_stats(closes[closes.index >= split], "1d")
    for label, mask in (("all", net.index >= net.index[0]), ("after", net.index >= split)):
        s = stats(net[mask], w[mask], "1d")
        out[label] = {k: s[k] for k in ("cagr", "sharpe", "dd")}
    out["btc_all"] = {k: hold["BTC hold"][k] for k in ("cagr", "sharpe", "dd")}
    out["btc_after"] = {k: hold_after["BTC hold"][k] for k in ("cagr", "sharpe", "dd")}
    return out


def main():
    state_path = HERE / "paper_state.json"
    if not state_path.exists():
        raise SystemExit("paper_state.json introuvable : lancez d'abord paper_trader.py")
    state = json.loads(state_path.read_text())
    live = state.get("live") or {}
    prices = live.get("prices") or state.get("last_closes", {})
    equity = live.get("equity", state["equity"])
    start_eq = state["start_equity"]

    # --- courbe d'equity (+ BTC « acheter et garder » à la même mise de départ)
    curve = [[int(pd.Timestamp(state["start"]).timestamp() * 1000), start_eq, None]]
    eq_path = HERE / "paper_equity.csv"
    if eq_path.exists():
        df = pd.read_csv(eq_path, parse_dates=["ts"])
        curve += [[int(t.timestamp() * 1000), float(e), (None if pd.isna(b) else float(b))]
                  for t, e, b in zip(df["ts"], df["equity"], df["btc"] if "btc" in df else [np.nan] * len(df))]
    btc0 = next((p[2] for p in curve if p[2]), None)
    curve[0][2] = btc0
    eqs = np.array([p[1] for p in curve])
    max_dd = float((eqs / np.maximum.accumulate(eqs) - 1).min())

    # --- positions
    positions = []
    for s, w in state["weights"].items():
        if not w:
            continue
        price = prices.get(s, state["last_closes"][s])
        usd = w * state["equity"] * price / state["last_closes"][s]
        entry = state["basis"].get(s, price)
        positions.append({"sym": s, "w": w, "usd": usd, "entry": entry, "price": price,
                          "pnl": (1 if w > 0 else -1) * (price / entry - 1)})
    invested = sum(abs(p["usd"]) for p in positions)

    # --- actifs : cours, score de tendance, courbe
    series = {s: recent_daily(s) for s in config.SYMBOLS}
    closes = pd.DataFrame(series).dropna()
    target = tsmom(closes, long_only=True).iloc[-1]
    vol = closes.pct_change().rolling(30).std().iloc[-1] * np.sqrt(365)
    assets = []
    for s in config.SYMBOLS:
        c = series[s]
        sma200 = c.rolling(200).mean()
        score = int(sum(c.iloc[-1] > c.iloc[-1 - L] for L in LOOKBACKS))
        price = prices.get(s, float(c.iloc[-1]))
        assets.append({
            "sym": s, "price": price, "chg": price / float(c.iloc[-1]) - 1,
            "score": score, "vol": float(vol[s]), "target": float(target[s]),
            "held": bool(state["weights"].get(s)),
            "close": [round(float(v), 6) for v in c.iloc[-SPARK_DAYS:]],
            "sma200": [None if pd.isna(v) else round(float(v), 6) for v in sma200.iloc[-SPARK_DAYS:]],
            "dates": [f"{d:%d/%m}" for d in c.index[-SPARK_DAYS:]],
        })

    data = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "start": state["start"], "start_equity": start_eq, "equity": equity,
        "bar": state["last_bar"], "strategy": config.STRATEGY,
        "bar_equity": state["equity"], "weights": state["weights"], "last_closes": state["last_closes"],
        "cash": equity - invested, "invested": invested, "max_dd": max_dd,
        "curve": curve, "positions": positions, "assets": assets,
        "trades": state["trades"][::-1][:200], "n_trades": len(state["trades"]),
        "costs": {"fee": config.FEE, "slip": config.SLIPPAGE},
        "bt": backtest_summary(),
    }
    html = (HERE / "dashboard_template.html").read_text(encoding="utf-8")
    html = html.replace("/*__DATA__*/null", json.dumps(clean(data), ensure_ascii=False, allow_nan=False))
    (HERE / "dashboard.html").write_text(html, encoding="utf-8")
    (HERE / "docs").mkdir(exist_ok=True)                    # dossier servi par GitHub Pages
    page = ('<!doctype html><html lang="fr"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<style>body{margin:0;font-size:14px}</style></head><body>' + html + '</body></html>')
    (HERE / "docs" / "index.html").write_text(page, encoding="utf-8")
    print(f"dashboard.html écrit — equity {equity:,.2f} ({equity / start_eq - 1:+.2%}), "
          f"{len(positions)} positions, {len(state['trades'])} ordres, {len(curve)} points de courbe")


if __name__ == "__main__":
    main()
