"""Paper trading : tourne en continu sur les vrais prix, avec de l'argent fictif.

Chaque minute, récupère les prix en direct des cryptos et calcule la valeur du
portefeuille au prix du marché. À chaque nouvelle bougie clôturée (config.TIMEFRAME),
recalcule les positions de la stratégie et passe les ordres fictifs, avec exactement
les mêmes calculs (frais, financement) que le backtest.

Fichiers écrits (lus par dashboard.py) :
  paper_state.json   état complet : on peut arrêter (Ctrl+C) et relancer sans rien perdre
  paper_trades.csv   un ordre par ligne
  paper_equity.csv   courbe d'equity, un point toutes les 15 minutes

Usage :  python paper_trader.py          (tourne en continu, une passe par minute)
         python paper_trader.py --once   (une seule passe puis arrêt, pour un planificateur)
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import config
from data import fetch_prices, fetch_recent
from engine import net_returns
from strategy import weights

STATE = Path("paper_state.json")
TRADES = Path("paper_trades.csv")
EQUITY = Path("paper_equity.csv")
POLL_SECONDS = 60
EQUITY_LOG_SECONDS = 900


def load():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"start": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "start_equity": config.STARTING_CASH, "equity": config.STARTING_CASH,
            "last_bar": None, "weights": {}, "basis": {}, "trades": [], "last_closes": {},
            "live": {}, "last_eq_log": 0}


def save(state):
    STATE.write_text(json.dumps(state, indent=2))


def append_csv(path, header, row):
    new_file = not path.exists()
    with path.open("a", encoding="utf-8") as f:
        if new_file:
            f.write(header + "\n")
        f.write(",".join(str(x) for x in row) + "\n")


def record_trade(state, ts, symbol, old, new, price):
    """Enregistre l'ordre et met à jour le prix d'entrée moyen de la position."""
    usd = abs(new - old) * state["equity"]
    if new == 0:
        state["basis"].pop(symbol, None)
    elif abs(new) > abs(old) and old * new >= 0:       # on ajoute à la position
        prev = state["basis"].get(symbol, price)
        state["basis"][symbol] = (prev * abs(old) + price * (abs(new) - abs(old))) / abs(new)
    elif old * new < 0:                                # retournement
        state["basis"][symbol] = price
    trade = {"ts": ts, "symbol": symbol, "from": old, "to": new, "price": price,
             "usd": round(usd, 2), "equity": round(state["equity"], 2)}
    state["trades"].append(trade)
    append_csv(TRADES, "ts,symbol,from,to,price,usd,equity", [trade[k] for k in ("ts", "symbol", "from", "to", "price", "usd", "equity")])
    side = "ACHAT" if new > old else "VENTE"
    print(f"   >>> {side:6} {symbol:10} {usd:>10,.0f} USDT à {price:,.4f}  (position {new:+.1%} du capital)")


def update(state):
    """Traite les nouvelles bougies clôturées. Renvoie True si l'état a changé."""
    bars = {s: fetch_recent(s, config.TIMEFRAME) for s in config.SYMBOLS}
    closes = pd.DataFrame({s: df["close"] for s, df in bars.items()}).dropna()
    last = closes.index[-1]
    if state["last_bar"] == str(last):
        return False
    w = weights(config.STRATEGY, bars, config.TIMEFRAME).reindex(closes.index).fillna(0)
    net = net_returns(w, closes, config.TIMEFRAME)
    first = state["last_bar"] is None
    if not first:
        new = net[net.index > pd.Timestamp(state["last_bar"])]
        state["equity"] *= float((1 + new).prod())
    target = {s: round(float(v), 4) for s, v in w.iloc[-1].items()}
    if first:                                          # ouverture initiale : on paie les frais d'entrée
        state["equity"] *= 1 - sum(abs(v) for v in target.values()) * (config.FEE + config.SLIPPAGE)
    for s, v in target.items():
        old = state["weights"].get(s, 0.0)
        if abs(v - old) > 1e-9:
            record_trade(state, str(last), s, old, v, float(closes[s].iloc[-1]))
    state["weights"], state["last_bar"] = target, str(last)
    state["last_closes"] = {s: float(closes[s].iloc[-1]) for s in closes.columns}
    invested = sum(abs(v) for v in target.values())
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] bougie {last:%Y-%m-%d %H:%M} UTC  capital "
          f"{state['equity']:,.2f} ({state['equity'] / state['start_equity'] - 1:+.2%})  investi {invested:.0%}")
    return True


def live(state):
    """Valeur du portefeuille au prix du marché en direct, entre deux bougies."""
    if not state.get("last_closes"):
        return
    prices = fetch_prices(config.SYMBOLS)
    pnl = sum(w * (prices[s] / state["last_closes"][s] - 1) for s, w in state["weights"].items())
    eq = state["equity"] * (1 + pnl)
    now = time.time()
    state["live"] = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "equity": eq, "prices": prices}
    if now - state["last_eq_log"] >= EQUITY_LOG_SECONDS:
        state["last_eq_log"] = now
        append_csv(EQUITY, "ts,equity,btc", [state["live"]["ts"], round(eq, 2), prices.get("BTC/USDT", "")])
    held = [f"{s.split('/')[0]} {w:.0%}" for s, w in state["weights"].items() if w]
    print(f"[{datetime.now():%H:%M}] direct  capital {eq:,.2f} ({eq / state['start_equity'] - 1:+.2%})  | "
          + (", ".join(held) if held else "100 % cash"))


def main():
    once = "--once" in sys.argv                    # une seule passe, pour un planificateur (GitHub Actions)
    state = load()
    print(f"Paper trading — {config.STRATEGY} en {config.TIMEFRAME} sur {len(config.SYMBOLS)} cryptos — "
          f"capital fictif {state['start_equity']:,.0f} USDT" + ("" if once else " — Ctrl+C pour arrêter"))
    while True:
        try:
            update(state)
            live(state)
            save(state)
        except Exception as e:                     # coupure réseau, limite API... on réessaie
            print(f"Erreur : {e}")
            if once:
                raise SystemExit(1)
        if once:
            return
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
