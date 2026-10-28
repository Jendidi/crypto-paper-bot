# Bot de trading crypto (paper trading)

Bot sur 25 cryptos avec **100 000 USDT fictifs**. Aucune clé API, aucun compte d'exchange, aucun ordre réel : le bot lit les prix publics de Binance et simule ses ordres, frais et glissement inclus.

## Comment il tourne 24h/24

Le workflow `.github/workflows/bot.yml` lance le bot **toutes les 15 minutes** sur les serveurs de GitHub (GitHub Actions, aux minutes 2, 17, 32 et 47) :

1. `paper_trader.py --once` rejoue toutes les bougies de 15 minutes terminées depuis la dernière passe : le résultat est le même quelle que soit l'heure exacte de la passe.
2. `dashboard.py` génère `docs/index.html`, la page de suivi servie par GitHub Pages.
3. L'état (`paper_state.json`, `paper_trades.csv`, `paper_equity.csv`) est enregistré dans le dépôt environ une fois par heure, ou dès qu'un ordre est passé.

La page de suivi lit en plus les prix en direct de Binance dans votre navigateur, toutes les 15 secondes. Les exécutions de GitHub peuvent avoir quelques minutes de retard. Pour lancer une passe tout de suite : onglet **Actions** du dépôt, workflow « bot », **Run workflow**.

## Stratégie : `blend` (décisions journalières)

À la clôture de chaque bougie journalière (00:00 UTC), le capital est partagé entre deux volets complémentaires :

- **Tendance (50 %)** : pour chaque crypto, le bot regarde si le prix est au-dessus de son niveau d'il y a 20, 50, 100 et 200 jours. Il n'achète qu'à partir de 3 horizons sur 4 (demi-position à 3/4, pleine à 4/4), avec une taille réduite pour les cryptos très volatiles. Rééquilibrage une fois par semaine.
- **Retours à la moyenne** : quand une crypto en tendance haussière (au-dessus de sa moyenne 200 jours) chute violemment (RSI 2 sous 5), le bot l'achète. Il revend au rebond (clôture au-dessus de la moyenne 5 jours), au stop (3 fois l'ATR sous le prix d'entrée) ou après 10 jours.

En marché baissier, les deux volets se mettent en cash d'eux-mêmes : le bot trade beaucoup en marché haussier et presque pas en marché baissier. Aucun levier : la somme des positions ne dépasse jamais 100 % du capital.

**Taille des positions : ×2 depuis la bougie du 27/10/2026** (×1 avant, réglage `SIZE_SCHEDULE`). Le compte n'a pas été remis à zéro. Avec ×2, un trade de retour à la moyenne risque environ 2 % du capital.

**Bande sans ordre : 2 % du capital, depuis la même date.** Une position n'est modifiée que si l'écart avec sa cible atteint 2 % du capital (les sorties complètes restent permises). Le plafond de 100 % ne limite que les nouveaux achats.

**Test sur le passé des décisions** (4 ans, 25 cryptos, frais, glissement et financement inclus, `python backtest_blend.py`) en ×2 avec la bande : +17,5 %/an, pire baisse de -31 %, 5,3 ordres par semaine. Par année : 2023 +31 %, 2024 +21 %, 2025 +22 %, 2026 -2 % (en cours). Depuis août 2025 (marché baissier) : +2,3 %/an contre -30 % pour le BTC. Rien ne garantit que cela se reproduise.

## Exécution des ordres (bougies de 15 minutes)

Les décisions restent journalières, mais les bougies de 15 minutes servent à choisir **le moment** (`execution.py`, réglages `EXEC` dans `config.py`) :

- **Achats** : la stratégie décide d'acheter à 00:00 UTC, mais l'ordre n'est passé qu'au premier bon moment des 24 heures suivantes : soit la baisse se stabilise (le prix repasse au-dessus de sa moyenne des 5 dernières heures avec une bougie verte), soit le prix est 0,5 % moins cher que le prix de décision. Au bout de 24 h, l'ordre passe au marché. Sur le test, les achats se font en moyenne 0,2 à 0,4 % moins cher, avec le même nombre d'ordres.
- **Ventes** : immédiates, au prix de clôture de la bougie.
- **Stop-loss de sécurité par position**, contrôlé à chaque bougie de 15 minutes : 25 % sous le prix d'entrée moyen pour BTC, ETH, BNB, LTC, XRP, 30 % pour les autres. Après une sortie sur stop, le bot attend 3 jours avant de racheter la même crypto.
- **Pas de take-profit fixe** : les sorties se font sur signal (rebond, fin de tendance, stop de la stratégie).
- **Budget d'ordres** : 12 ordres maximum sur 7 jours glissants (les sorties complètes restent permises).

**Test sur 2 ans de cette exécution** (`python backtest_exec.py`) : +19,5 %/an, pire baisse de -22 %, 4,8 ordres par semaine. Sans stop ni budget : +23,6 %/an, 5,5 ordres par semaine. Chaque ordre est exécuté au prix de clôture de la bougie qui le déclenche.

## Ce qui a été testé et écarté

- **Trading actif en bougies 1h** (`active.py`, `backtest_active.py` : long et short, stops sur structure de 3 à 7 %, TP partiel, breakeven, risque 1 %) : -28,5 %/an, un peu pire que des entrées au hasard. Les trades de range sont le principal perdant.
- **Décider à chaque bougie de 15 minutes** (`intraday.py`, `backtest_15m.py`, `download_15m.py`) : +3,4 %/an et 43 ordres par semaine, contre +22,5 %/an et 5,4 ordres pour la version journalière sur la même période.
- **Stops et take-profits serrés par position** : stop 8-12 % : +9 %/an ; stop 10-15 % : +10 % ; stop 10-15 % avec TP 25 % : +6 % ; contre +23,6 % sans. Le bot se fait sortir par le bruit, puis rachète plus cher. Des stops de 25-30 % ne coûtent que 2 à 4 points.
- **Ventes à découvert en tendance**, **momentum relatif entre cryptos** et **stratégies 1h/4h** : perdantes une fois les frais payés.
- Le compte précédent (`tsmom_lo`, 10 cryptos, tendance seule) est archivé dans `archive/`.

## Fichiers

| Fichier | Rôle |
|---|---|
| `config.py` | Réglages : cryptos, capital, frais, taille, exécution |
| `strategy.py` | Les stratégies journalières (celle utilisée est `blend`) |
| `execution.py` | Exécution des ordres sur bougies de 15 minutes, stops, budget |
| `engine.py` | Calcul du portefeuille, des frais et des statistiques |
| `data.py` | Prix via l'API publique de Binance |
| `paper_trader.py` | Le bot (`--once` pour une seule passe) |
| `dashboard.py` + `dashboard_template.html` | Génèrent la page de suivi |
| `backtest_blend.py`, `backtest_timing.py`, `backtest_exec.py` | Tests de la stratégie et de l'exécution |
| `research*.py`, `sensitivity.py`, `backtest.py`, `active.py`, `backtest_active.py`, `intraday.py`, `backtest_15m.py` | Recherche et stratégies écartées |

## En local (optionnel)

```
pip install -r requirements.txt
python paper_trader.py     # tourne en continu
python dashboard.py        # génère docs/index.html
python backtest_blend.py   # test des décisions sur 4 ans
python backtest_exec.py    # test de l'exécution sur 2 ans (nécessite download_15m.py)
```
