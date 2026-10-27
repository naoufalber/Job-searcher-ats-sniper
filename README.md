# ATS Sniper

Le script surveille les ATS d'entreprises configurés, ainsi que les recherches
globales HelloWork et Welcome to the Jungle. Une offre est enregistrée dans
`jobs_seen.db` avant l'envoi de la notification ; une notification échouée est
retentée au scan suivant.

## Exécution

```bash
pip install -r requirements.txt
python -m unittest -v
python ats_sniper.py
```

Le workflow GitHub Actions lance un scan toutes les 5 minutes (`*/5`). GitHub
peut néanmoins décaler une tâche planifiée en période de forte charge. Le mode
local `python ats_sniper.py --loop` utilise le même intervalle par défaut.

## Configuration

Les secrets de notification restent ceux déjà utilisés :

- `DISCORD_WEBHOOK_URL`
- `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID`

Variables utiles pour élargir ou limiter les recherches :

- `HELLOWORK_QUERIES` : termes séparés par des virgules ;
- `HELLOWORK_LOCATION` : localisation HelloWork, `France` par défaut ;
- `HELLOWORK_MAX_PAGES` : 2 par défaut, 30 offres environ par page ;
- `WTTJ_QUERIES` : termes séparés par des virgules ;
- `WTTJ_FILTERS` : filtre Algolia WTTJ, limité par défaut à la France et aux contrats temps plein ;
- `WTTJ_MAX_HITS` : nombre maximal de résultats par terme, 200 par défaut ;
- `ATS_SCAN_INTERVAL_SECONDS` : intervalle du mode `--loop`, 300 secondes par défaut.

Les identifiants Algolia WTTJ sont récupérés automatiquement depuis son endpoint
public à chaque exécution. `WTTJ_ALGOLIA_APP_ID` et `WTTJ_ALGOLIA_API_KEY` peuvent
être fournis en variables d'environnement si ce endpoint est temporairement
bloqué sur l'environnement d'exécution.

Au premier lancement avec une base vide, les offres déjà présentes sont
enregistrées sans alerte afin d'éviter un faux rattrapage massif. Les offres
apparues entre deux scans sont dédupliquées par leur identifiant de plateforme.
