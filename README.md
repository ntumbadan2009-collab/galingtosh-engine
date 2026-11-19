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
- TTS : Edge TTS est essayé en premier ; si le service en ligne échoue, le moteur utilise le modèle Piper français embarqué (`fr_FR-siwis-medium`) et mesure l'audio réellement produit. La voix Piper utilise les données SIWIS (CC BY 4.0) : https://datashare.is.ed.ac.uk/handle/10283/2353. Pour les autres langues, Edge TTS reste nécessaire tant qu'un modèle local correspondant n'est pas installé.
- Rendu 4K sur Render Free : le moteur refuse les sorties dépassant 2,07 mégapixels (profil mémoire 1080p) ; les ressources CPU/RAM, la durée et la taille peuvent aussi imposer un échec. 720p est le profil recommandé.
- Effets ou transitions non répertoriés : avertissement et comportement de repli.

## Déploiement
Le dépôt fournit un Dockerfile et un render.yaml pour un service web Render Free. Configurer les secrets `SUPABASE_SERVICE_ROLE_KEY` et `ENGINE_SHARED_SECRET` dans Render. Ne jamais committer ces secrets.
Le worker tourne dans le processus web : conserver une seule instance pour éviter les workers concurrents, et prévoir le réveil après mise en veille de Render avec `POST /wake`.

## Contrat Supabase
Le moteur utilise uniquement les tables, colonnes, RPC et buckets décrits dans le contrat Galingtosh. Il ne crée ni ne modifie le schéma Supabase. Les seules écritures applicatives sont les mises à jour autorisées de `render_jobs` et les dépôts dans `renders` / `temp-assets`.

## API
- `GET /health` : santé du service.
- `GET /capabilities` : capacités annoncées.
- `POST /media/probe` : analyse protégée d’un média référencé dans `media_assets`.
- `POST /render/validate` : validation Film JSON, protégé par `X-Engine-Secret`.
- `POST /wake` : réveil du worker, protégé.
- `GET /tasks/{job_id}` : statut et étape, protégé.

## Variables d'environnement
`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `ENGINE_SHARED_SECRET`, `WORKER_ID`, `POLL_INTERVAL_SECONDS`, `MAX_RENDER_SECONDS`, `MAX_OUTPUT_MB`.

## Tests
GitHub Actions installe Python 3.12 et FFmpeg, puis exécute `pytest -q` à chaque push et pull request. Pour un test local : installer FFmpeg/ffprobe, installer `requirements.txt`, puis lancer `pytest -q`. Les tests Supabase en direct nécessitent un projet et des données de test dédiés.


## Correctifs du 17 novembre 2026
Les migrations et fonctions Edge sont maintenant versionnées dans `supabase/`. La migration additive `20261117190000_consistent_project_workflow.sql` a été appliquée au projet Galingtosh 2. Elle ajoute la création atomique projet/film, la journalisation atomique des opérations et leur annulation, le verrouillage des versions envoyées au rendu, la réutilisation des rendus actifs et l’annulation utilisateur.

Le worker maintient son bail pendant toute la production, vérifie son identité avant chaque écriture et refuse de livrer un rendu dont un média référencé ou une narration demandée est indisponible. Les transitions préservent la durée du montage en prolongeant la dernière image sortante pendant le recouvrement ; `inSec` positionne un plan dans sa scène, tandis que `sourceInSec` désigne un éventuel point d’entrée dans le fichier source.

Validation locale : 50 tests Python avec FFmpeg, 4 tests Deno des opérations du film et vérification TypeScript des fonctions. Les tests transactionnels sur Supabase (création, conflit de révision, version figée, dédoublonnage, annulation) ont été exécutés avec rollback.
