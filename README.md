# Galingtosh Engine

Moteur de rendu déterministe de Galingtosh 2. Le moteur vidéo utilise Python + FFmpeg ; aucune génération IA d'image ou de vidéo n'est intégrée.

## État du dépôt

- API FastAPI : `/health`, `/capabilities`, `/render/validate`, `/wake`, `/tasks/{job_id}`.
- Client Supabase REST : lecture des versions de films et des références `media_assets`, lecture des jobs, claim atomique via RPC, heartbeat/progression par PATCH limité aux colonnes autorisées, upload Storage limité à `renders` et `temp-assets`.
- Worker mono-job : claim, lecture Film JSON, résolution upload/search, rendu MP4, crédits JSON, upload, statut final.
- Résolution search : URL HTTP(S) seulement, vérification DNS contre IP non publiques et contrôle du MIME réel ; les redirections sont validées à chaque saut.
- Médias 3D, audio, TTS, sous-titres, effets avancés, graphiques/SVG et rendu programmatique restent incomplets.
- Le rendu actuel produit une piste vidéo sans audio. Les jobs qui nécessitent une bande sonore ne sont donc pas encore conformes au cahier des charges complet.
- Aucun schéma SQL, table, colonne, bucket ou RPC n'est créé/modifié par ce dépôt.

## Configuration

Variables : `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `ENGINE_SHARED_SECRET`, `WORKER_ID`, `POLL_INTERVAL_SECONDS`, `MAX_RENDER_SECONDS`, `MAX_OUTPUT_MB`. Ne jamais placer les clés dans le code ou les journaux.

Le worker ne démarre que si la clé service_role et le secret interne sont configurés. Le secret est comparé en temps constant sur les routes protégées.

## Contrat de stockage

- Lecture des médias uploadés uniquement depuis `user-uploads/{user_id}/...`.
- Sorties uniquement vers `renders/{project_id}/{job_id}.mp4` et, si des médias de recherche sont présents, `{job_id}.credits.json`.
- Seules les colonnes `status, progress, output_path, error, warnings, finished_at` de `render_jobs` sont modifiables.
- Les RPC `claim_render_job` et `requeue_stale_render_jobs` doivent déjà exister conformément au contrat Supabase communiqué. Ce moteur ne les crée pas.

## Exécution

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
pytest -q
```

Le worker démarre au lancement si ses secrets sont configurés. `POST /wake` accepte `X-Engine-Secret`. Le worker vérifie les statuts avant/après les phases coûteuses et nettoie son répertoire temporaire.

## Limites de déploiement

Render Free est éphémère et contraint en mémoire/CPU. Un seul rendu est traité à la fois ; une interruption brutale peut nécessiter la RPC de réattribution des tâches périmées. Vérifier le comportement de veille et de réveil sur le service déployé avant production.
