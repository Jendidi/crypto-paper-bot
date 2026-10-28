"""Paper trading : tourne avec de l'argent fictif sur les vrais prix de Binance.

Les décisions sont journalières (stratégie `blend`, positions cibles à la clôture de 00:00 UTC). L'exécution se fait sur les
bougies de 15 minutes : un achat attend le bon moment (la baisse se stabilise, ou prix 0,5 % moins cher) pendant 24 h au
maximum, les ventes sont immédiates, chaque position a un stop-loss contrôlé toutes les 15 minutes, et un budget limite le
nombre d'ordres sur 7 jours glissants (voir execution.py et config.EXEC).

À chaque passe, le bot rejoue toutes les bougies de 15 minutes terminées depuis la précédente : le résultat ne dépend donc pas de
l'heure exacte à laquelle il tourne. Chaque ordre est exécuté au prix de clôture de la bougie qui l'a déclenché, frais et glissement
inclus. Si un jour est incomplet, il est repris à la passe suivante.

Fichiers écrits (lus par dashboard.py) :
  paper_state.json   état complet : positions, ordres en attente, prix d'entrée, compteur d'ordres...
  paper_trades.csv   un ordre par ligne
  paper_equity.csv   courbe d'equity, un point par passe enregistrée

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
from data import fetch_prices, fetch_recent, fetch_since
from execution import advance
from strategy import weights

STATE = Path("paper_state.json")
TRADES = Path("paper_trades.csv")
EQUITY = Path("paper_equity.csv")
POLL_SECONDS = 60
EQUITY_LOG_SECONDS = 900
WARMUP = pd.Timedelta(days=4)           # bougies 15 min relues avant la dernière traitée (moyenne de référence)


def migrate(state):
    """Reprise d'un compte tenu en bougies journalières : on continue bougie de 15 minutes par bougie, sans rupture."""
    if "pending" in state:
        return state
    day = pd.Timestamp(state["last_bar"])                      # dernier jour traité (la bougie ouvre à 00:00)
    state["decided_day"] = str(day)
    state["last_bar"] = str(day + pd.Timedelta(hours=23, minutes=45))
    prev = dict(state["weights"])
    for t in state["trades"]:
        t.setdefault("exec", str(pd.Timestamp(t["ts"]) + pd.Timedelta(days=1)))
        t.setdefault("reason", "")
        if t["ts"] == str(day):
            prev[t["symbol"]] = t["from"]                      # le coût de ces changements est facturé à la bougie suivante
    state["prev_weights"] = prev
    state["pending"], state["cooldown"], state["orders_ts"] = {}, {}, []   # le budget d'ordres repart de zéro
    state["entry"] = dict(state.get("basis", {}))
    return state


def load():
    if STATE.exists():
        return migrate(json.loads(STATE.read_text()))
    last = fetch_since(config.SYMBOLS[0], "15m", pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(hours=6)).index[-1]
    return {"start": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "start_equity": config.STARTING_CASH, "equity": config.STARTING_CASH,
            "last_bar": str(last), "decided_day": str(last.normalize()), "weights": {}, "prev_weights": {}, "entry": {},
            "basis": {}, "cooldown": {}, "pending": {}, "orders_ts": [], "trades": [], "last_closes": {}, "live": {},
            "last_eq_log": 0}


def save(state):
    STATE.write_text(json.dumps(state, indent=2))
    with TRADES.open("w", encoding="utf-8") as f:
        f.write("exec,symbol,from,to,price,usd,equity,reason\n")
        for t in state["trades"]:
            f.write(",".join(str(t.get(k, "")) for k in ("exec", "symbol", "from", "to", "price", "usd", "equity", "reason")) + "\n")


def append_csv(path, header, row):
    new_file = not path.exists()
    with path.open("a", encoding="utf-8") as f:
        if new_file:
            f.write(header + "\n")
        f.write(",".join(str(x) for x in row) + "\n")


def record_trade(state, ts, symbol, old, new, price, why):
    usd = abs(new - old) * state["equity"]
    trade = {"ts": ts, "exec": ts, "symbol": symbol, "from": old, "to": new, "price": price,
             "usd": round(usd, 2), "equity": round(state["equity"], 2), "reason": why}
    state["trades"].append(trade)
    side = "ACHAT" if new > old else "VENTE"
    print(f"   >>> {ts[:16]} UTC  {side:6} {symbol:10} {usd:>10,.0f} USDT à {price:,.4f}  (position {new:+.1%} du capital, {why})")


def update(state):
    """Rejoue les bougies de 15 minutes terminées depuis la dernière passe. Renvoie leur nombre."""
    t_last = pd.Timestamp(state["last_bar"])
    raw = {s: fetch_since(s, "15m", t_last - WARMUP) for s in config.SYMBOLS}
    closes = pd.DataFrame({s: b["close"] for s, b in raw.items()}).dropna()
    opens = pd.DataFrame({s: b["open"] for s, b in raw.items()}).reindex(closes.index)
    barsd = {s: fetch_recent(s, "1d", limit=1000) for s in config.SYMBOLS}
    wd = weights(config.STRATEGY, barsd, "1d")
    n = advance(state, closes, opens, wd, record=lambda ts, s, o, nw, px, why: record_trade(state, ts, s, o, nw, px, why))
    state["basis"] = dict(state["entry"])
    if n:
        invested = sum(abs(v) for v in state["weights"].values())
        print(f"[{datetime.now():%Y-%m-%d %H:%M}] {n} bougie(s) de 15 min traitée(s), dernière {state['last_bar'][:16]} UTC  capital "
              f"{state['equity']:,.2f} ({state['equity'] / state['start_equity'] - 1:+.2%})  investi {invested:.0%}  "
              f"en attente {len(state['pending'])}")
    return n


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
    print(f"Paper trading — {config.STRATEGY}, décisions journalières, exécution sur bougies 15 min — {len(config.SYMBOLS)} cryptos — "
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
