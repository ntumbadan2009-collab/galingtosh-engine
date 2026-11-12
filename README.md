# Galingtosh Engine

Moteur de rendu vidéo autonome de Galingtosh 2. Le dépôt est séparé de l'application mobile et du backend existant.

## État réel — étape 1

- Opérationnel dans cette première base : API FastAPI, endpoint public de santé, inspection indicative de FFmpeg, validation initiale du Film JSON, protection par secret partagé de la route de validation.
- Pas encore implémenté : client Supabase, récupération/claim des tâches, rendu FFmpeg, stockage, boucle worker, audio, sous-titres, TTS, graphiques/SVG et annulation.
- Aucun endpoint ne prétend lancer un rendu à ce stade.

## Démarrage local

Python 3.12 et FFmpeg sont requis.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

`GET /health` est public. `GET /capabilities` décrit l'état réel des capacités. `POST /render/validate` exige l'en-tête `X-Engine-Secret`.

## Variables d'environnement

Voir `.env.example`. Les secrets ne doivent jamais être commités. Le projet Supabase Galingtosh 2 configuré est `https://lmlwekcytivszlszmfvy.supabase.co`.

## Contrat de données

Le moteur doit consommer le contrat `render_jobs`, RPC `claim_render_job` et `requeue_stale_render_jobs`, `films.data`, `media_assets` et les buckets `user-uploads`, `renders`, `temp-assets` spécifiés pour Galingtosh 2. Aucun schéma SQL ni table supplémentaire n'est créé par ce dépôt. Les écritures autorisées seront limitées à `render_jobs` (champs explicitement autorisés) et aux buckets de sortie/temporaire.

## Tests

```bash
pytest -q
```

Les tests présents couvrent uniquement le validateur initial et les routes HTTP de cette étape. Les tests d'intégration Supabase nécessiteront des variables d'environnement et des données de test dédiées.

## Déploiement Render

Créer un Web Service depuis ce dépôt avec le Blueprint `render.yaml`. Renseigner `SUPABASE_SERVICE_ROLE_KEY` et `ENGINE_SHARED_SECRET` dans les variables secrètes Render. Vérifier ensuite `/health`. L'endpoint de réveil et le worker de tâches ne sont pas encore disponibles ; ne pas configurer le backend pour les appeler avant leur livraison.
