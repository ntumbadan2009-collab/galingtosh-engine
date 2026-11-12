# Galingtosh Engine

Moteur de rendu autonome de Galingtosh 2, indépendant de l'application mobile.

## État réel — étape 3 (pipeline vidéo initial)

- API FastAPI, validation initiale Film JSON et client Supabase REST.
- Renderer déterministe d'images et de vidéos locales vers MP4 H.264/yuv420p.
- Images fixes et mouvements Ken Burns/zoom/pan/tilt via filtres FFmpeg.
- Découpage temporel des plans, remplissage des intervalles absents par du noir, limitation de durée et de taille, inspection finale ffprobe.
- Médias manquants et types non supportés signalés en warnings.
- Les transitions Film JSON sont pour l'instant rendues en coupes franches avec avertissement.
- Audio, sous-titres, TTS, effets avancés, graphiques/SVG et résolveur média Supabase ne sont pas encore livrés.
- Le worker automatique et l'endpoint `/wake` ne sont pas activés.

## Utilisation Python

```python
from pathlib import Path
from app.core.renderer import FilmRenderer

result = await FilmRenderer(max_seconds=600, max_output_mb=45).render(
    film_json, {"media-id": Path("/tmp/media/image.jpg")}, Path("/tmp/final.mp4")
)
```

Les fichiers média doivent être préalablement téléchargés et vérifiés par un résolveur sécurisé. Ne passez jamais un chemin fourni directement par un client sans le confiner à un répertoire de travail.

## API et Supabase

Voir les étapes précédentes dans ce README et `.env.example`. Aucune table, colonne, RPC ou bucket n'est créé ou modifié ici. Les écritures Supabase autorisées restent limitées aux colonnes listées de `render_jobs` et aux buckets `renders` / `temp-assets`.

## Tests

`pytest -q` exécute les tests unitaires et le test FFmpeg (si FFmpeg/ffprobe sont installés). Ces tests sont ajoutés au dépôt mais doivent encore être exécutés dans un environnement Python/FFmpeg réel avant toute mise en production.
