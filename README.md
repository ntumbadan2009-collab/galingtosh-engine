# Galingtosh Engine

Moteur de rendu déterministe de Galingtosh 2. L'application mobile transmet un Film JSON ; le moteur récupère les médias autorisés, assemble les plans avec FFmpeg et stocke le MP4 final. Aucune génération IA d'image ou de vidéo n'est utilisée.

## État de cette version

- API FastAPI : santé, capacités et validation du Film JSON.
- Worker séquentiel activé au démarrage lorsque `SUPABASE_SERVICE_ROLE_KEY` est configurée.
- Réclamation atomique via `claim_render_job`, récupération des tâches bloquées via `requeue_stale_render_jobs`, polling et réveil HTTP protégé.
- Lecture des versions immuables de `films.data` et des médias référencés dans `media_assets`.
- Téléchargement des uploads privés et des médias de recherche avec contrôle MIME et protections SSRF pour les URL externes.
- Rendu déterministe des images et vidéos locales en MP4 H.264 ; transitions selon le module FFmpeg présent.
- Upload du MP4 dans `renders/{project_id}/{job_id}.mp4` et, si nécessaire, d'un fichier de crédits JSON.
- État de tâche lisible via `GET /tasks/{job_id}` ; réveil du worker via `POST /wake`.

## Limites connues

Le moteur actuel ne réalise pas encore le mixage audio, les sous-titres, le TTS, les graphiques, les SVG ni les effets avancés. Les crédits sont exportés mais doivent encore être vérifiés au regard des licences réelles des fournisseurs. Les rendus 1080p/4K ne sont pas garantis sur l'offre Render Free. Le moteur ne crée ni table, ni colonne, ni RPC, ni bucket Supabase.

Le worker s'appuie sur les RPC et tables déjà définis dans le contrat du projet. Sans ces objets côté Supabase, il restera en échec de connexion aux tâches ; aucune migration n'est exécutée automatiquement.

## Configuration

Variables d'environnement : `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `ENGINE_SHARED_SECRET`, `WORKER_ID`, `POLL_INTERVAL_SECONDS`, `MAX_RENDER_SECONDS`, `MAX_OUTPUT_MB`.

Ne jamais placer les clés dans le dépôt ou dans les journaux. `/wake`, `/tasks/{job_id}` et `/render/validate` exigent l'en-tête `X-Engine-Secret`.

## Tests

Exécuter `pytest -q` dans un environnement Python 3.12 avec FFmpeg et ffprobe installés. Les tests d'intégration Supabase doivent utiliser un projet de test et des données dédiées.
