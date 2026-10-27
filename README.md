# Bot de trading crypto (paper trading)

Bot sur 25 cryptos avec **100 000 USDT fictifs**. Aucune clé API, aucun compte d'exchange, aucun ordre réel : le bot lit les prix publics de Binance et simule ses ordres, frais et glissement inclus.

## Comment il tourne 24h/24

Le workflow `.github/workflows/bot.yml` lance le bot **toutes les heures** sur les serveurs de GitHub (GitHub Actions) :

1. `paper_trader.py --once` met à jour le portefeuille fictif et enregistre l'état dans `paper_state.json`, `paper_trades.csv` et `paper_equity.csv`.
2. `dashboard.py` génère `docs/index.html`, la page de suivi servie par GitHub Pages.
3. Le résultat est enregistré dans le dépôt (un commit « bot: état du … »).

La page de suivi lit en plus les prix en direct de Binance dans votre navigateur, toutes les 15 secondes. L'état du bot (ordres, courbe d'equity) est, lui, mis à jour toutes les heures. Les exécutions de GitHub peuvent avoir quelques minutes de retard.

Pour lancer une passe tout de suite : onglet **Actions** du dépôt, workflow « bot », **Run workflow**.

## Stratégie : `blend` (tendance + retours à la moyenne)

Le bot décide à la clôture de chaque bougie journalière (00:00 UTC). Le capital est partagé entre deux volets complémentaires :

- **Tendance (50 %)** : pour chaque crypto, le bot regarde si le prix est au-dessus de son niveau d'il y a 20, 50, 100 et 200 jours. Il n'achète qu'à partir de 3 horizons sur 4 (demi-position à 3/4, pleine à 4/4), avec une taille réduite pour les cryptos très volatiles. Rééquilibrage une fois par semaine pour limiter les frais.
- **Retours à la moyenne** : quand une crypto en tendance haussière (au-dessus de sa moyenne 200 jours) chute violemment (RSI 2 sous 5), le bot l'achète. Il revend au rebond (clôture au-dessus de la moyenne 5 jours), au stop (3 fois l'ATR sous le prix d'entrée) ou après 10 jours. La taille est calculée pour ne risquer que **1 % du capital** par trade.

En marché baissier, les deux volets se mettent en cash d'eux-mêmes : le bot trade beaucoup en marché haussier et presque pas en marché baissier. Aucun levier : la somme des positions ne dépasse jamais 100 % du capital.

**Taille des positions : ×2 depuis la bougie du 27/10/2026** (×1 avant, réglage `SIZE_SCHEDULE` dans `config.py`). Le compte n'a pas été remis à zéro : le calcul du passé reste en ×1, seul l'avenir passe en ×2. Avec ×2, un trade de retour à la moyenne risque 2 % du capital (1 % en ×1), et jusqu'à 10 positions peuvent s'ouvrir en même temps après une chute généralisée.

**Bande sans ordre : 2 % du capital, depuis la bougie du 27/10/2026.** Le bot ne modifie une position que si l'écart avec sa cible atteint 2 % du capital (les sorties complètes restent toujours permises). Cela évite les micro-ordres : sur le test, le nombre d'ordres passe de 13,7 à 5,3 par semaine (toutes cryptos confondues) sans perte de rendement. Le plafond de 100 % du capital ne limite que les nouveaux achats : il ne re-calcule jamais les positions déjà détenues.

**Test sur le passé** (4 ans, 25 cryptos, frais, glissement et financement inclus, `python backtest_blend.py`) en ×2 avec la bande : +17,5 %/an, pire baisse de -31 %. Par année : 2023 +31 %, 2024 +21 %, 2025 +22 %, 2026 -2 % (en cours). Depuis août 2025 (marché baissier) : +2,3 %/an contre -30 % pour le BTC. En ×1 sans bande : +8,4 %/an et -20 % de pire baisse. Le ratio rendement/risque est à peu près identique : on mise plus sur le même pari, et le gain en plus vient surtout de 2023-2025. Rien ne garantit que cela se reproduise.

## Ce qui a été testé et écarté

- **Trading actif en bougies 1h** (`active.py`, `backtest_active.py` : long et short, stops sur structure de 3 à 7 %, TP partiel, breakeven, risque 1 %) : -28,5 %/an, un peu pire que des entrées au hasard. Les trades de range sont le principal perdant. Avec des stops plus larges et un filtre de tendance journalière : entre -1 et +5 %/an, négatif depuis septembre 2025.
- **Suivi toutes les 15 minutes** (`intraday.py`, `backtest_15m.py`, `download_15m.py`) : mêmes signaux, évalués à chaque bougie de 15 minutes, testés sur 2 ans. Résultat : +3,4 %/an et 43 ordres par semaine, contre +22,5 %/an et 5,4 ordres pour la version journalière sur la même période. Ne surveiller que le stop toutes les 15 minutes donne +17,1 %/an et 14 ordres par semaine, toujours moins bien. Les décisions restent donc journalières.
- **Ventes à découvert en tendance** : trop sensibles aux réglages pour être fiables.
- **Momentum relatif entre cryptos** et **stratégies 1h/4h** : perdantes une fois les frais payés.
- Le compte précédent (`tsmom_lo`, 10 cryptos, tendance seule) est archivé dans `archive/`.

## Fichiers

| Fichier | Rôle |
|---|---|
| `config.py` | Réglages : cryptos, capital, frais, stratégie |
| `strategy.py` | Les stratégies (celle utilisée est `blend`) |
| `engine.py` | Calcul du portefeuille, des frais et des statistiques |
| `data.py` | Prix via l'API publique de Binance |
| `paper_trader.py` | Le bot (`--once` pour une seule passe) |
| `dashboard.py` + `dashboard_template.html` | Génèrent la page de suivi |
| `backtest_blend.py` | Test de la stratégie utilisée |
| `research*.py`, `sensitivity.py`, `backtest.py`, `active.py`, `backtest_active.py` | Recherche et stratégies écartées |

## En local (optionnel)

```
pip install -r requirements.txt
python paper_trader.py     # tourne en continu
python dashboard.py        # génère docs/index.html
python backtest_blend.py   # test sur 4 ans
```
