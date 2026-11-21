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

Avec `include_sample_frames: true`, le moteur extrait une image JPEG réelle toutes les 5 secondes sur la fenêtre inspectée (jusqu'à 60 images pour 300 secondes). Elles sont envoyées uniquement à l'agent authentifié pour une évaluation de leur pertinence visuelle.

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

**Évaluation visuelle partielle intégrée :** l'agent peut examiner les images échantillonnées toutes les 5 secondes, en groupes limités avec un délai de traitement avec une intention de plan et obtenir une proposition de candidat. C'est un aperçu, pas une certification du passage complet : les actions dans le temps et les plans non échantillonnés restent non vérifiés.

**Phase 2 nécessaire** : observation de plusieurs images successives de chaque passage pertinent, compréhension des événements/mouvements, analyse de continuité avec les plans voisins, validation des droits et sélection définitive selon l'intention narrative.

## Validation du rendu

Une plage vidéo `sourceInSec + (outSec - inSec)` qui dépasse la durée
disponible de la vidéo source est maintenant rejetée au lieu d'être masquée
par un gel silencieux de la dernière image.

## Déploiement

Cette fonctionnalité doit passer les tests FFmpeg/Python et Deno/TypeScript,
puis un test de rendu réel avec le moteur et l'agent avant déploiement. Une
branche non fusionnée n'affecte pas le service Render de production.

Le résultat de l'agent précise `sampledFrameCount`, `visionReviewedCount`, `samplingIntervalSec = 5` et `reviewIncomplete`. Si le budget de temps est atteint, toutes les images n'auront pas nécessairement été interprétées par la vision ; l'analyse reste partielle et n'est jamais présentée comme exhaustive.
