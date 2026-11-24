# Consolidation niveaux 1–12 — candidat expérimental
Le marqueur d'exécution reste editorialLevel 5 afin de préserver les contrôles stricts existants. Aucun changement de contrat de durée ou de stockage.
- N9 : mesure LUFS, true peak et plage dynamique sur l'audio réellement décodé du rendu final. Les avertissements sont des indicateurs techniques, pas une évaluation émotionnelle ni une écoute de la narration. L'analyse sémantique et les essais de musique/voix réelles restent à valider.
- N10 : restaurer les checkpoints d'une scène en bloc seulement si tous les fichiers correspondent au manifeste, sans écraser les scènes déjà encodées. Signature du rendu liée aux empreintes des sources réelles. Limite existante 600 s / 45 Mo : aucun support de durée supérieure annoncé; reprise entre jobs et publication multi-segments restent à développer.
- N11 : préférences explicites et révocables par projet, valeurs bornées et défaut neutre; consentement via action authentifiée, aucun profilage automatique, aucun partage interprojet. Interface client et test E2E restant.
- N12 : rapport de livraison structurel, contrôle strict du rapport technique du même rendu, mesures audio distinguées de l'écoute et du jugement artistique. Les protections visuelles et la livraison SQL existantes restent obligatoires. Aucun score inventé. Autonomie intégrale pas démontrée.
## Zoom back / release
1. Suite Python + Deno, tests d'encodage, preuve de reprise, tests de non-régression des niveaux 1–8.
2. MP4 hybride A/B, examen par le vrai fournisseur vision (pas de mock) et sélection privée liée à la preuve. Le workflow bloque si les secrets du fournisseur de test sont absents. Ne pas copier de secrets de production dans les sources ni dans les logs.
3. MP4 150 secondes : inspecter les rapports et le fichier, puis contrôle humain du son, du mouvement, des sous-titres et de la pertinence.
4. Tester migrations 003/004 et agent Supabase ensemble en environnement isolé; les transactions SQL de CI seules ne démontrent pas une migration réelle. Tester l'action de révision, conflits et consentement avec les clients web/Android.
5. Ne fusionner main (déploiement automatique Render) qu'après validation du candidat exact et coordination avec Supabase. Garder le précédent commit live et vérifier /, les logs et un rendu réel après publication.
