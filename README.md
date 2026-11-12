# Galingtosh Engine

Moteur de montage audiovisuel déterministe de Galingtosh 2. Le moteur reçoit un Film JSON, résout les médias autorisés, construit les plans et assemble le résultat avec Python et FFmpeg. **Aucune API de génération IA d'image ou de vidéo n'est utilisée.**

## Fonctions implémentées
- Images fixes et vidéos : recadrage, mise à l'échelle, durée, cadence, mouvements Ken Burns, zoom, panoramique et inclinaison.
- Montage multi-scènes, trous temporels remplacés par du noir, coupes et transitions dissolve/fade/slide/zoom/wipe.
- Mixage audio multipiste avec placement temporel, volume en dB, boucle de musique, limiteur et encodage AAC.
- Sous-titres SRT incrustés ; export de crédits de médias recherchés.
- Effets déterministes : fondu d'entrée/sortie, niveaux de gris, vignettage et texte incrusté.
- Graphiques barres/lignes/circulaires générés à partir de spécifications JSON et rasterisation SVG contrôlée.
- API FastAPI santé/capacités/validation, worker séquentiel, réveil protégé et lecture du statut des tâches.
- Résolution de médias privés Supabase et médias publics avec contrôle MIME, limite de taille, validation DNS/IP et validation de chaque redirection.

## Non pris en charge
- Modèles 3D et rendu 3D.
- Génération de médias par IA.
- TTS : aucune voix n'est synthétisée dans cette version. Les pistes TTS sans fichier audio sont signalées comme avertissement.
- Rendu 4K/1080p sur Render Free : les résolutions peuvent être demandées mais les ressources CPU/RAM, la durée et la taille peuvent imposer un échec. 720p est le profil recommandé.
- Effets ou transitions non répertoriés : avertissement et comportement de repli.

## Déploiement
Le dépôt fournit un Dockerfile et un render.yaml pour un service web Render Free. Configurer les secrets `SUPABASE_SERVICE_ROLE_KEY` et `ENGINE_SHARED_SECRET` dans Render. Ne jamais committer ces secrets.
Le worker tourne dans le processus web : conserver une seule instance pour éviter les workers concurrents, et prévoir le réveil après mise en veille de Render avec `POST /wake`.

## Contrat Supabase
Le moteur utilise uniquement les tables, colonnes, RPC et buckets décrits dans le contrat Galingtosh. Il ne crée ni ne modifie le schéma Supabase. Les seules écritures applicatives sont les mises à jour autorisées de `render_jobs` et les dépôts dans `renders` / `temp-assets`.

## API
- `GET /health` : santé du service.
- `GET /capabilities` : capacités annoncées.
- `POST /render/validate` : validation Film JSON, protégé par `X-Engine-Secret`.
- `POST /wake` : réveil du worker, protégé.
- `GET /tasks/{job_id}` : statut et étape, protégé.

## Variables d'environnement
`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `ENGINE_SHARED_SECRET`, `WORKER_ID`, `POLL_INTERVAL_SECONDS`, `MAX_RENDER_SECONDS`, `MAX_OUTPUT_MB`.

## Tests
GitHub Actions installe Python 3.12 et FFmpeg, puis exécute `pytest -q` à chaque push et pull request. Pour un test local : installer FFmpeg/ffprobe, installer `requirements.txt`, puis lancer `pytest -q`. Les tests Supabase en direct nécessitent un projet et des données de test dédiés.
