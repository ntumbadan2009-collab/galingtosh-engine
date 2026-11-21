# Sélection des extraits vidéo — phase 1

## But
Permettre à l'agent réalisateur de choisir le point d'entrée d'un extrait dans
une vidéo source, tout en conservant une chronologie distincte pour le film.

- `shot.inSec` : début du plan sur la chronologie de sa **scène**.
- `shot.outSec` : fin du plan sur la chronologie de sa **scène**.
- `shot.sourceInSec` : début de la lecture dans la **vidéo source**.

Exemple : le plan commence à 00:06 de la scène, dure 4 secondes,
mais utilise le passage de 01:12 à 01:16 d'une vidéo source.
Alors : `inSec = 6`, `outSec = 10`, `sourceInSec = 72`.

## Inspecter des candidats

`POST /media/inspect-clips`

Authentification : JWT utilisateur Supabase dans `Authorization: Bearer <token>`.
Le serveur valide le jeton et vérifie le propriétaire du média.

Requête :

```json
{
  "project_id": "uuid-du-projet",
  "media_id": "uuid-du-media",
  "user_id": "uuid-utilisateur",
  "min_clip_seconds": 1,
  "max_clip_seconds": 12,
  "scene_threshold": 0.3
}
```

La réponse indique :
- la durée totale et la durée effectivement inspectée ;
- les passages détectés avec `startSec`, `endSec`, `durationSec` ;
- `analysisLevel = shot_boundaries_only` ;
- `requiresSemanticReview = true` et `semanticVerified = false` pour chaque candidat.

La recherche initiale limite l'analyse à 300 secondes et 120 passages afin de
ne pas épuiser les ressources Render. Si la durée réelle est supérieure,
`inspectionTruncated` est vraie : **aucune conclusion ne doit être tirée
sur la partie non analysée**.

## Sélection sémantique

Cette phase utilise la détection **technique** des changements visuels. Elle ne
reconnaît pas encore les actions, les animaux, les personnes, les sujets ou la
correspondance avec un texte narratif. La fonction `choose_reviewed_passage`
peut classer des candidats **uniquement après** réception de scores provenant
d'une vraie analyse visuelle (pertinence, qualité, continuité).

Le modèle réalisateur ne doit pas inventer ces scores ni conclure qu'une
séquence montre une action sur la seule base du nom du média.

**Phase 2 nécessaire** : échantillonnage de plusieurs images par passage,
vision-langage ou modèle multimodal, prise en compte de la durée et des
événements, analyse de continuité avec les plans voisins, et sélection des
extraits selon l'intention narrative.

## Validation du rendu

Une plage vidéo `sourceInSec + (outSec - inSec)` qui dépasse la durée
disponible de la vidéo source est maintenant rejetée au lieu d'être masquée
par un gel silencieux de la dernière image.

## Déploiement

Cette fonctionnalité doit passer les tests FFmpeg/Python et Deno/TypeScript,
puis un test de rendu réel avec le moteur et l'agent avant déploiement. Une
branche non fusionnée n'affecte pas le service Render de production.
