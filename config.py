"""Paramètres du bot. Modifiez ici, pas dans le code."""

# Prix : API publique de Binance (voir data.py). Panier de test : 10 cryptos parmi les plus liquides. Ce n'est pas une recommandation.
SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
           "ADA/USDT", "DOGE/USDT", "LINK/USDT", "AVAX/USDT", "LTC/USDT"]
HISTORY_DAYS = 1460       # 4 ans d'historique pour le backtest

# Réglages du paper trader
STRATEGY = "tsmom_lo"     # suivi de tendance, long seul (la plus robuste aux tests de sensibilité)
TIMEFRAME = "1d"          # tsmom_lo ne fonctionne qu'en bougies journalières

# Capital fictif (partagé entre toutes les cryptos)
STARTING_CASH = 100000.0  # en USDT
# Sans levier : la somme des positions (en valeur absolue) ne dépasse jamais le capital.

# Coûts réalistes de contrats perpétuels (nécessaires pour vendre à découvert)
FEE = 0.0005              # 0,05 % par ordre (frais « taker »)
SLIPPAGE = 0.0003         # 0,03 % d'écart de prix à l'exécution
FUNDING_PER_DAY = 0.0003  # ~0,03 %/jour de frais de financement des positions (≈ 11 %/an)

# Part de l'historique réservée au test « hors échantillon » (la fin)
OUT_OF_SAMPLE = 0.3
