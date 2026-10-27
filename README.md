# Bot de trading crypto (paper trading)

Bot de suivi de tendance sur 10 cryptos, avec **100 000 USDT fictifs**. Aucune clé API, aucun compte d'exchange, aucun ordre réel : le bot lit les prix publics de Binance et simule ses ordres.

## Comment il tourne 24h/24

Le workflow `.github/workflows/bot.yml` lance le bot **toutes les heures** sur les serveurs de GitHub (GitHub Actions) :

1. `paper_trader.py --once` met à jour le portefeuille fictif et enregistre l'état dans `paper_state.json`, `paper_trades.csv` et `paper_equity.csv`.
2. `dashboard.py` génère `docs/index.html`, la page de suivi servie par GitHub Pages.
3. Le résultat est enregistré dans le dépôt (un commit « bot: état du … »).

La page de suivi lit en plus les prix en direct de Binance dans votre navigateur, toutes les 15 secondes. L'état du bot (ordres, courbe d'equity) est, lui, mis à jour toutes les heures. Les exécutions de GitHub peuvent avoir quelques minutes de retard.

Pour lancer une passe tout de suite : onglet **Actions** du dépôt, workflow « bot », **Run workflow**.

## Stratégie : `tsmom_lo`

Pour chaque crypto, le bot regarde si le prix est au-dessus de son niveau d'il y a 20, 50, 100 et 200 jours. Il n'est acheteur que si au moins 3 horizons sur 4 sont haussiers (3/4 = demi-position, 4/4 = position pleine). La taille est réduite pour les cryptos très volatiles, le total ne dépasse jamais 100 % du capital, et le portefeuille n'est rééquilibré qu'une fois par semaine pour limiter les frais : le bot décide avec la clôture du lundi, donc ses ordres passent le mardi à 00:00 UTC. Sinon, le bot reste en cash.

Test sur 4 ans, frais inclus : +12,6 %/an avec une pire baisse de -26 %, contre +40,9 %/an et -53 % pour le BTC gardé. Depuis août 2025 (marché baissier) : -9,4 %/an contre -27,8 %. Rien ne garantit que cela se reproduise.

## Fichiers

| Fichier | Rôle |
|---|---|
| `config.py` | Réglages : cryptos, capital, frais, stratégie |
| `strategy.py` | Les stratégies (celle utilisée est `tsmom_lo`) |
| `engine.py` | Calcul du portefeuille, des frais et des statistiques |
| `data.py` | Prix via l'API publique de Binance |
| `paper_trader.py` | Le bot (`--once` pour une seule passe) |
| `dashboard.py` + `dashboard_template.html` | Génèrent la page de suivi |
| `backtest.py`, `research.py`, `sensitivity.py` | Tests sur le passé et tests de robustesse |

## En local (optionnel)

```
pip install -r requirements.txt
python paper_trader.py     # tourne en continu
python dashboard.py        # génère docs/index.html
python backtest.py         # compare les stratégies sur 4 ans
```
