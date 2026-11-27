# Candidat V34 — recherche Web sécurisée

Base: V33, branche rebuild/stable-2026-11-26. Ne pas fusionner main ni déployer Supabase avant test isolé.

- Brave Search API (BRAVE_SEARCH_API_KEY, côté serveur): références images, vidéos, 3D et actualité, SafeSearch strict. Les références de recherche ne sont jamais des assets importables; leur date de page n'est pas la date d'un événement. Les titres ne sont pas des preuves.
- Candidats importables: Art Institute of Chicago (public domain explicite), Internet Archive (métadonnées par fichier et licence explicite, assertion du déposant à vérifier), Smithsonian (SMITHSONIAN_API_KEY, média marqué CC0, aperçu raster de 3D uniquement). Conserver auteur, lien, droits et date si disponible. Les droits de marque, vie privée et droits de tiers restent à contrôler.
- Extension importable bloquée par défaut: SECURE_WEB_MEDIA_ENABLED=true requis séparément dans l'agent ET le moteur, uniquement en staging. Aucun accès anonyme aux nouveaux endpoints. Aucun fichier HTML, script, ZIP, playlist ou modèle 3D exécutable.
- Téléchargement HTTPS sur domaines sources autorisés, DNS public et contrôle de chaque redirection; MIME et signature, tailles, format vidéo et flux; réencodage des images; décodage FFmpeg local sans variables de secrets; modération des images et de la planche vidéo échantillonnée, hash SHA256 des octets contrôlés à nouveau au rendu. La modération et les filtres ne garantissent pas zéro contenu abusif.
- Les modèles GLB/OBJ/Blender externes sont exclus de l'import réel, jusqu'à un worker de conversion hors réseau sans secrets, avec limites CPU/RAM/disque. Une image d'illustration 3D reste possible.
- La recherche actualité fournit des pistes; ne prétend pas vérifier les événements. Pour documents récents, vérifier source primaire, date effective, lieu et preuve indépendante; aucun média générique présenté comme une image de l'événement.
- Avant activation: scanner et sandbox OS dédiée sans secrets/montages sensibles/egress; tests de corruption, décompression, DNS rebinding, régression FFmpeg; vérifier licences de chaque fournisseur et faux positifs de modération; limiter quotas et timeouts; test complet avec vrais fournisseurs et plusieurs durées. La V33 reste inchangée.

## Publication progressive
L'agent et search-media peuvent découvrir les métadonnées de sources institutionnelles même lorsque l'import est désactivé. Ces résultats sont renvoyés uniquement sous web_references (sans identifiant attachable ni URL de téléchargement). Brave est borné à trois références par recherche. L'import reste bloqué jusqu'à validation du worker isolé.
