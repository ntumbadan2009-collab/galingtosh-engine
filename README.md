# Galingtosh Engine

Moteur de rendu vidéo autonome de Galingtosh 2. Dépôt indépendant de l'application mobile et du backend existant.

## État réel — étape 2

- Opérationnel dans le code : API FastAPI, santé, capacités FFmpeg, validation initiale du Film JSON, authentification par secret partagé, client Supabase REST, lecture d'une tâche et du Film JSON, RPC de claim/requeue, patch limité aux colonnes autorisées de `render_jobs`, upload limité aux buckets `renders` et `temp-assets`.
- Tests présents : validation, API et client Supabase mocké.
- Pas encore implémenté : boucle worker active, rendu FFmpeg, téléchargement média sécurisé/SSRF, stockage de sortie utilisé par un pipeline, audio, sous-titres, TTS, graphiques/SVG et annulation pilotée par le worker.

**Le claim n'est pas appelé automatiquement.** On évite de réserver des jobs de production avant que le pipeline de rendu soit prêt.

## Configuration

Python 3.12 et FFmpeg requis. Copier `.env.example` vers `.env`, puis renseigner les secrets localement. Ne jamais commiter le fichier `.env`.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
pytest -q
```

Routes : `GET /health`, `GET /capabilities`, `POST /render/validate` et `GET /tasks/{job_id}`. Les deux dernières exigent `X-Engine-Secret`.

## Contrat Supabase

Projet Galingtosh 2 : `https://lmlwekcytivszlszmfvy.supabase.co`.

Le client utilise uniquement le contrat communiqué : `render_jobs`, `films.data`, `media_assets`, RPC `claim_render_job` et `requeue_stale_render_jobs`. Les PATCH sur `render_jobs` sont limités à `status, progress, output_path, error, warnings, finished_at`. Les uploads sont autorisés seulement vers `renders` et `temp-assets`. Aucun SQL, table, colonne ou fonction n'est créé par ce dépôt.

Le client ne journalise ni clé, ni contenu de réponse d'erreur, ni URL signée. Le téléchargement des médias de recherche et la protection SSRF seront livrés avec la couche médias avant activation du worker.

## Déploiement Render

Le Blueprint `render.yaml` configure un Web Service Docker Free. Renseigner `SUPABASE_SERVICE_ROLE_KEY` et `ENGINE_SHARED_SECRET` dans les variables secrètes du service. Le worker de rendu n'est pas encore activé : ne pas encore connecter le backend à un endpoint `/wake`.
