"""Paramètres du bot. Modifiez ici, pas dans le code."""

# Prix : API publique de Binance (voir data.py). Panier de test : 10 cryptos parmi les plus liquides. Ce n'est pas une recommandation.
SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
           "ADA/USDT", "DOGE/USDT", "LINK/USDT", "AVAX/USDT", "LTC/USDT",
           "DOT/USDT", "ATOM/USDT", "UNI/USDT", "NEAR/USDT", "TRX/USDT",
           "ETC/USDT", "XLM/USDT", "BCH/USDT", "FIL/USDT", "AAVE/USDT",
           "ALGO/USDT", "VET/USDT", "INJ/USDT", "OP/USDT", "APT/USDT"]
HISTORY_DAYS = 1460       # 4 ans d'historique pour le backtest

# Réglages du paper trader
STRATEGY = "blend"        # moitié suivi de tendance, moitié retours à la moyenne avec stop (voir strategy.blend)
TIMEFRAME = "1d"          # tsmom_lo ne fonctionne qu'en bougies journalières

# Taille des positions : multiplicateur selon la date de la bougie. x2 à partir du 27/10/2026 (décidé en cours de route,
# sans nouveau compte : avant cette date le calcul reste en x1). Test sur 4 ans : x1 = +8,4 %/an, pire baisse -20 % ;
# x2 = +15,9 %/an, pire baisse -34 %. Avec x2, un trade de retour à la moyenne risque 2 % du capital (1 % en x1).
SIZE_SCHEDULE = [("1970-01-01", 1.0), ("2026-10-27", 2.0)]

# Bande sans ordre : une position n'est modifiée que si l'écart avec sa cible dépasse 2 % du capital (les sorties complètes
# restent toujours permises). Évite les micro-ordres. Test sur 4 ans en x2 : 13,7 -> 5,2 ordres par semaine, rendement inchangé.
NO_TRADE_BAND = 0.02
NO_TRADE_BAND_FROM = "2026-10-27"      # même principe que la taille : le passé du compte n'est pas recalculé

# Capital fictif (partagé entre toutes les cryptos)
STARTING_CASH = 100000.0  # en USDT
# Sans levier : la somme des positions (en valeur absolue) ne dépasse jamais le capital.

# Coûts réalistes de contrats perpétuels (nécessaires pour vendre à découvert)
FEE = 0.0005              # 0,05 % par ordre (frais « taker »)
SLIPPAGE = 0.0003         # 0,03 % d'écart de prix à l'exécution
FUNDING_PER_DAY = 0.0003  # ~0,03 %/jour de frais de financement des positions (≈ 11 %/an)

# Stratégie active (active.py) : long et short, bougies 1h, tendance lue sur les bougies 4h.
# Les valeurs viennent de vos règles ; on ne les ajuste pas pour « faire joli » sur le passé.
MAKER_FEE = 0.0002        # ordres limites (take-profit) : 0,02 %
ACTIVE = dict(
    risk_per_trade=0.01,      # on ne perd jamais plus de 1 % du capital sur un trade (frais inclus)
    sl_min=0.03,              # stop-loss : au moins 3 % du prix d'entrée...
    sl_cap_major=0.05,        # ...au plus 5 % sur BTC, ETH, BNB, LTC, XRP...
    sl_cap_alt=0.07,          # ...et 7 % sur les altcoins plus volatiles. Au-delà, on ne prend pas le trade.
    majors=("BTC/USDT", "ETH/USDT", "BNB/USDT", "LTC/USDT", "XRP/USDT"),
    tp1_r=1.0,                # TP1 à 1:1 : on sécurise 50 % et le stop passe au prix d'entrée
    tp_r_min=2.0,             # objectif final : entre 1:2 et 1:3,
    tp_r_max=3.0,             # calé sur la zone de liquidité (plus haut / plus bas récent) quand elle est dans cette plage
    tp_cap=0.15,              # jamais plus de 15 %
    max_hold_bars=168,        # un trade dure 7 jours au maximum
    score_min=2,              # nombre de confirmations demandées en tendance (RSI, rejet, cassure, croisement)
    bear_extra=1,             # confirmation de plus exigée quand le BTC est en tendance baissière
    max_concurrent=4,         # positions ouvertes en même temps (2 si le BTC est baissier)
    max_concurrent_bear=2,
    max_open_risk_trades=3,   # au plus 3 trades « à risque » (pas encore au breakeven) = 3 % du capital en jeu
    max_gross=1.0,            # somme des positions <= 100 % du capital : pas de levier
    cooldown_bars=6,          # on attend 6 h avant de rejouer une crypto sortie sur stop
    regime_gap=0.015,         # tendance 4h : EMA50 au moins 1,5 % au-dessus (ou en dessous) de l'EMA200
    allow_short=True,         # ventes à découvert autorisées
    allow_range=True,         # trades de range (bas/haut du canal) autorisés
    daily_filter=False,       # filtre de sens sur la tendance JOURNALIÈRE (même signal que tsmom_lo)
    dscore_min=2,             # achats si au moins 3 horizons journaliers sur 4 sont haussiers, ventes si au moins 3 sont baissiers
)

# Part de l'historique réservée au test « hors échantillon » (la fin)
OUT_OF_SAMPLE = 0.3
