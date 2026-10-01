# Résumés de session

## 2026-09-29 — Audit et fondations

- Création du dépôt GitHub privé et audit de son état initial vide.
- Point de retour Git vide publié avant toute modification de fichier : `1207757`.
- Python 3.12.14 détecté ; `pytest` absent et aucune dépendance installée.
- Début de la Phase 1 : contrats JSON, configuration TOML et progression structurée.
- Phase 1 terminée : contrats Planner/Coder, validation de progression, configuration TOML et suite de tests sans dépendance.
- Vérification exécutée avec Python 3.12.14 : 28 tests `unittest` réussis ; aucune dépendance installée.
- Phase 2 : adaptateur Gemini Interactions API et routeur ordonné ajoutés ; 42 tests simulés réussis. Aucun appel réel effectué, car aucun modèle/quota n'a été confirmé.
- Adaptateurs NVIDIA Build et Groq ajoutés au format Chat Completions compatible OpenAI ; chargement du `.env` local sans écraser les variables du processus. Présence des trois noms de clés vérifiée sans lire leurs valeurs. Les modèles restent non configurés ; aucun appel API réel effectué.
- Vérification après intégration : 44 tests `unittest` réussis ; `git diff --check` propre.
- Phase 3 : gestionnaire d'exécution contrôlée ajouté avec aperçu, approbation, contrôle des chemins sensibles, comparaison d'empreintes, sauvegarde et restauration atomique. 50 tests réussis dans le dossier source du projet, y compris le refus d'un lien symbolique.
- Phase 4 : vérificateur déterministe ajouté. Il n'exécute que les commandes exactes de la liste autorisée, avec `shell=False`, limite de temps, sortie expurgée des secrets et résultats structurés. Plafond de deux corrections validé par test. 55 tests réussis (un test de lien symbolique ignoré dans le checkout de développement).
- Phase 5 : CLI et workflow Planner/Coder ajoutés. Le plan JSON est stocké en attente et n'entre dans la progression qu'après approbation ; les propositions sont validées et prévisualisées sans écriture, puis l'apply exige une confirmation interactive et crée une sauvegarde. La vérification n'exécute que les commandes exactes autorisées ; les corrections restent limitées à deux après échec. 66 tests réussis et aide CLI vérifiée ; aucun appel API réel effectué.

## 2026-09-29 — UI-01 Shell et état des fournisseurs

- UI-01 : shell local desktop ajouté (sidebar, header, workspace, panneau contextuel et barre d’état) avec la palette directement fournie pour le logo Codelix.
- Le pont UI est limité à `127.0.0.1`, lecture seule, et ne retourne que les compteurs de tâches, routes non secrètes et état Git. Les vues futures n’affichent aucune donnée fictive.
- Aucune dépendance installée et aucun appel provider lancé pour construire l’interface.
- Validation : 3 tests UI ciblés et 69 tests `unittest` complets réussis ; commande `ui` visible dans l’aide CLI.
- Diagnostics provider consignés : GET Gemini modèles HTTP 200, génération minimale HTTP 503 ; GET NVIDIA modèles HTTP 200, POST complétion timeout ~300 s ; GET Groq modèles HTTP 403. La phase 2 reste en revue.


## 2026-09-29 — UI-03 à UI-10 et synchronisation

- Chat Planner, Tasks, Agents/Models, Files/Changes, Verification, Git/History et Settings sont reliés aux états du projet et aux composants existants. Les actions de modèle, d’exécution et d’application restent déclenchées explicitement.
- Les cartes Planner, Coder, Tester et Verifier affichent une progression calculée depuis les tâches achevées et vérifications enregistrées. Les propositions en attente restent en revue.
- Finition visuelle selon la palette du logo, glassmorphisme discret, respect des préférences de mouvement/transparence et correction des boutons Files gris natifs.
- Contrôles statiques Python AST, JavaScript, JSON, TOML et `git diff --check` réussis. Aucun test ni appel IA n’a été lancé pendant cette phase. La CSS servie localement sur l’onglet ouvert répond HTTP 200 avec les règles Files attendues.
- Phase 2 reste en revue : aucun succès de génération fournisseur n’est confirmé.

## 2026-09-30 — Migration Vybelix et passation

- Migration du package, de la CLI, de la configuration neuve et du branding terminée; compatibilité historique conservée en attendant la validation d’installation Python 3.12.
- Commit `bc4a9aa` publié sur `Vybelix/Vybelix` `main`; les changements distants préexistants ont été intégrés avant le push.
- 71 tests `unittest` réussis et aides des deux CLI vérifiées avec Python 3.14.7. La construction de wheel n’a pas abouti car setuptools était absent et l’interpréteur n’était pas dans la plage Python 3.12 déclarée.
- Copie complète du cahier des charges dans `docs/progress/PROJECT_BRIEF.md`; le fichier source local est ignoré par Git mais conservé. Le suivi JSON ajoute la tâche de migration terminée et la validation d’installation à faire.
- `.env` non consulté ni modifié. La Phase 2 fournisseurs reste en revue; aucun appel modèle réel n’a été effectué.

## 2026-09-30 — UI-11 : verre lumineux et tâches simplifiées

- Thème glassmorphism bleu-violet étendu à l’ensemble de l’interface : fond atmosphérique, panneaux translucides, bordures lumineuses, navigation, champs et boutons.
- Vue Tâches remaniée en liste : compteurs par état, section À traiter, tâches terminées repliées et détails techniques accessibles à la demande. Libellés de navigation francisés.
- `git diff --check` est propre sur les ressources UI. Aucun test automatisé n’a été lancé. Ces changements sont locaux et non commités.

- Affinage UI-11 selon la nouvelle référence : nappes lumineuses cyan et magenta animées derrière les surfaces, contours en dégradé et alpha de verre renforcé. Principes du skill `kmp-glassmorphism-ui` adaptés au front-end HTML/CSS (pas de composants Kotlin ajoutés); les préférences de réduction du mouvement et de transparence restent prises en compte. `git diff --check` propre; aucun test automatisé lancé.

- Écran Assistant adapté à la référence : titre centré, grande zone de message vitrée et bouton d’envoi; les cartes de suggestions prédéfinies ont été supprimées à la demande. Le plan réel reste dessous. Diff check uniquement; aucun test automatisé lancé.

- Précision de la demande : suppression totale des suggestions prédéfinies de l’écran Assistant; conservation des mêmes coins généreusement arrondis et de la même matière glass violette sombre sur le champ et le cadre. Le statut de reprise pointe sur cette version.

- Contrôle visuel de l’Assistant à 1200 × 800 : champ glass sans double fond opaque ni poignée de redimensionnement, largeur 559 px et coins arrondis conservés. Ajustement vertical pour afficher tout l’écran et le plan récent sans défilement.
- Police Sora ajoutée globalement via Google Fonts; la famille variable couvre les graisses usuelles et les titres utilisent ExtraBold 800. Chargement vérifié dans le navigateur; connexion Internet requise pour récupérer la police.
- Fond ambiant global réglé en violet sombre `#10091F` au lieu du noir; en-tête, navigation et barre d’état harmonisés sans perdre l’effet glass des panneaux.
- Séparation des vues qui partageaient le même rendu par erreur : Terminal suit les opérations de session et mène vers Vérification; Vérification garde ses commandes autorisées et résultats; Git n’affiche que l’état et les commits; Historique n’affiche que les événements enregistrés par Vybelix.
- Suite aux repères de l’utilisateur, contour en verre dégradé et angles arrondis (24 px) ajoutés au conteneur commun des vues, donc visibles dans toute l’application; variante opaque accessible selon `prefers-reduced-transparency`.
- Espacement de 8 px ajouté entre les rangées-cartes successives des panneaux (commits Git, etc.) afin d’éviter qu’elles se collent.
- Après retour utilisateur, surfaces glass partagées assombries plus nettement dans toute l’app (conteneur, cartes, contexte et compositeur) en baissant uniquement l’opacité; teintes et accents conservés.
- Couleur de tout le texte et des placeholders uniformisée en blanc via une règle globale couvrant l’ensemble des vues.
- Lisibilité renforcée uniquement par la typographie (libellés secondaires 12 px minimum, graisse 500 et interligne 1.5); aucune couleur changée pour cette passe.


## 2026-09-30 — UI-12 Paramètres API KEYS

- Ajout de la page Paramètres → API KEYS pour saisir/remplacer ou supprimer les clés des fournisseurs configurés dans `vybelix.toml`. Les champs sont masqués; les réponses serveur ne contiennent que le statut configuré/non configuré.
- Au premier accès, création et confirmation d’un PIN à six chiffres. Dérivé PBKDF2-HMAC-SHA256 salé dans le cache local ignoré par Git; suspension de 60 secondes après cinq échecs; jeton en mémoire expirant après 15 minutes d’inactivité.
- Les clés sont mises à jour atomiquement dans `.env`, qui est déjà ignoré par Git. Le PIN ne chiffre pas ce fichier; cette limite est indiquée dans l’interface et la doc fournisseurs.
- Syntaxe Python en mémoire, `node --check` et `git diff --check` réussis. Aucun test automatisé ni appel réseau/API exécuté. Dépôt laissé non commité/non poussé.


## 2026-09-30 — Ajustement du gestionnaire API Keys

- À la demande, le panneau inline est remplacé par un bouton qui ouvre une fenêtre glass. Après le PIN, le gestionnaire liste les noms de variables sans valeurs, permet d’ajouter plusieurs paires nom/clé, de remplacer une clé ou de la supprimer.
- Les noms de variables exacts `api_key_env` des fournisseurs configurés sont acceptés; les noms personnalisés doivent se terminer par `_API_KEY` et peuvent être reliés dans `vybelix.toml`.
- Valeurs toujours masquées et stockées localement dans `.env` ignoré. Syntaxes Python/JS et diff check réussis; aucun test automatisé ni appel réseau. Non commité/non poussé.


## 2026-09-30 — Aperçu frontend autonome API Keys

- À la demande, le parcours API Keys est repassé en aperçu front-end uniquement : modal, PIN simulé, formulaire nom/clé, entrées multiples, remplacement/retrait uniquement en mémoire. Aucun fetch vers `/api/keys`, aucune lecture/écriture `.env`, aucune valeur transmise au backend.
- La valeur de clé saisie est effacée immédiatement après la validation de démonstration; PIN et entrées simulées disparaissent au rechargement. Le branchement backend/fournisseurs est volontairement en attente afin de ne pas empiéter sur le travail parallèle.
- `node --check` et `git diff --check` réussis; aucun test automatisé. Dépôt non commité/non poussé.


## 2026-09-30 — Démarrage Skill Builder

- Première tranche locale basée sur le cahier des charges fourni : modules `src/vybelix/skills/`, schémas manifest/capabilities, commande CLI de brouillon/validation/installation/activation/désactivation/désinstallation, registre et audit locaux.
- Installation uniquement depuis un dossier local, désactivée après copie, avec confirmation interactive; activation vérifie l’accord exact sur les permissions. Contrôles de fichiers/liens/taille/secrets et empreinte d’intégrité ajoutés.
- L’exécution de skill reste explicitement bloquée; aucun téléchargement ni appel fournisseur n’est fait. Interface, dépendances, mises à jour et sandbox OS constituent la suite. Spécification archivée dans `docs/skills/SPEC_SKILL_BUILDER.md`.
- Vérifications statiques seulement prévues; aucun test automatisé lancé. Changements locaux non commités/non poussés.


## 2026-09-30 — Vue Skills du cockpit

- Ajout navigation et écran Skills : création de brouillon, affichage des skills installés et dossiers sous `skills/`, résultat de validation, permissions et avertissements, installation désactivée et actions avec confirmations.
- Routes UI locales liées à `SkillManager`; les chemins API sont limités aux sources sous `skills/`, l’activation confirme exactement les permissions choisies, et aucune capability n’est exécutée.
- Contrôles statiques Python/JS et `git diff --check` réussis; aucun test automatisé lancé. Sandbox OS, dépendances, mises à jour et intégration de sources distantes restent en attente. Non commité/non poussé.


## 2026-09-30 — Assombrissement global des surfaces

- À la demande, harmonisation de toutes les surfaces glass sur un violet/bleu nuit proche de la référence : conteneurs, cartes, colonnes, saisies, navigation, chat, modales et éléments API/Skills.
- Réduction de l’intensité des bordures claires, des reflets et des halos au survol; palette d’accents, texte et arrondis conservés. Adaptation également du mode `prefers-reduced-transparency`.
- `node --check` et `git diff --check` réussis; aucun test automatisé lancé. Changements locaux non commités/non poussés.


## 2026-09-30 — Routes modèles UI, validation Python 3.12 et progression

- La page Modèles peut ajouter ou retirer des candidats pour Planner/Coder/Tester, définir l’ordre principal/secours et enregistrer les listes dans `[models]` du TOML actif. Le backend n’accepte que les fournisseurs présents dans la configuration, des IDs valides et au plus cinq candidats; mise à jour atomique, les autres tables TOML sont préservées.
- Le formulaire Paramètres → API Keys lie maintenant l’enregistrement d’une clé au choix d’un modèle, rôle et priorité. La clé reste dans `.env` local; le `.env` n’est pas chiffré. Aucun appel génération n’a été lancé.
- Python 3.12.10 : wheel `vybelix-0.1.0` construite et installée dans un venv temporaire; imports `vybelix` et compatibilité `codelix`, ressource `ui_assets/index.html`, commandes CLI vérifiés.
- Suite complète : 77 tests `unittest` réussis. Première exécution: la nouvelle fixture route n’avait pas le fournisseur Gemini configuré; fixture corrigée, puis suite complète réussie.
- `tasks.json`, `PROJECT_STATUS.md` et `NEXT_CODEX.md` mis à jour. Phase fournisseurs maintenue `needs_review` faute de validation des accès API sur tous les comptes. Travail Skill Builder conservé séparément et toujours en cours.


## 2026-09-30 — Visite guidée de Vybelix

- Ajout d’un guide de première visite et d’un bouton `?` pour le relancer : étapes couvrant Accueil, Assistant, Agents, Vérification, Skills, Paramètres et API Keys.
- Le parcours reprend les bulles de présentation fournies : écran assombri, cible encadrée, carte claire près de l’élément, compteur, Ignorer, Retour, Suivant et Terminé; Escape et flèches gauche/droite sont pris en charge.
- Les étapes API Keys expliquent l’accès via Paramètres et l’ajout de clés fournisseurs. Le guide ne soumet aucun formulaire et ne modifie aucune clé.
- Contrôles statiques après implémentation; aucun test automatisé lancé dans cette passe. Changements locaux non commités/non poussés.


## 2026-09-30 — Clôture technique de la Phase 2

- Suite complète Python 3.12.10 : 77 tests réussis, dont erreurs HTTP, fallback/retries, adaptateurs et routes UI.
- Appels contrôlés directs, 30 s, sans retry : Gemini 401; NVIDIA HTTP 200 mais réponse JSON non-streamée sans texte exploitable; Groq 403; OpenRouter 401; Mistral 429. Aucune valeur de clé ni header affiché.
- Historique : NVIDIA `openai/gpt-oss-20b` a répondu `OK` en streaming et Planner/Coder ont réussi via cette route; Gemini a répondu une fois puis a rencontré des 503.
- Aucune configuration de routes, clé, tâche ou fichier projet produit par l’IA n’a été modifié; aucun workflow Planner/Coder/Tester n’a été lancé. Phase 2 reste `needs_review` jusqu’à rétablissement des accès et confirmation d’un appel NVIDIA streaming actuel.
- Vérification supplémentaire du chemin NVIDIA SSE par défaut : `openai/gpt-oss-20b` renvoie HTTP 200 et `OK` en 0,9 s.


## 2026-09-30 — Tests finaux des routes et fallback 401

- Le routeur continue vers un candidat de secours configuré après HTTP 401, sans retry sur la clé refusée; si aucun candidat suivant n’existe, il signale l’erreur. Tests ajoutés pour ces deux cas.
- Les prompts Planner/Coder énumèrent désormais les champs exacts requis par leurs contrats JSON. Suite complète Python 3.12.10 : 78 tests réussis.
- Modèles uniques testés directement, une fois chacun (timeout 30 s, sans retry) : NVIDIA `openai/gpt-oss-20b` a répondu `OK`; NVIDIA `z-ai/glm-5.3` a expiré; Gemini `gemini-3.8-flash` et `gemini-3.7-flash` ont répondu HTTP 401; Groq `openai/gpt-oss-20b` a répondu HTTP 403.
- Smoke Planner : fallback Gemini→NVIDIA confirmé, première réponse au format legacy rejetée par le validateur; après amélioration du prompt, la requête Planner a expiré sur NVIDIA GPT-OSS et GLM après 30 s chacun. Coder et vérification non atteints.
- Aucun code généré appliqué ou exécuté. L’approbation automatique a rejeté cette étape car aucune proposition exacte n’avait été examinée; le test a été arrêté sans contournement. Aucune clé ni route active modifiée. Phase 2 reste `needs_review`.
- Le prompt précise également que `schema_version` doit valoir exactement la chaîne `1.0`; 78 tests réussis après cet ajustement. Dernier smoke Planner au délai réel configuré : Gemini 401, NVIDIA GPT-OSS puis GLM expirés à 60 s. Aucun plan valide, donc pas de Coder/Verifier.


## 2026-09-30 — Retest OpenRouter et Mistral

- OpenRouter `openai/gpt-oss-20b` : un appel SSE minimal, erreur réseau sans statut HTTP après 42,1 s.
- Mistral `mistral-small-latest` : HTTP 429 immédiat. Aucun retry; aucune clé affichée.


## 2026-10-01 — Contexte compact et reprise contrôlée

- Ajout de `ProjectContextStore` : fichier local `.vybelix-cache/context.json`, association à l’identifiant du projet, taille maximale 64 Ko, schéma strict, chemins secrets refusés, motifs de secrets/API filtrés et écriture atomique.
- Ajout CLI `vybelix context show` et `vybelix context update <json>`; les commandes n’appellent aucun modèle.
- Paramètres du cockpit contient un éditeur du contexte local via `/api/context`; le texte précise qu’il n’est pas transmis automatiquement aux modèles.
- Ajout de `vybelix resume --task-id ...` et bouton « Reprendre la tâche » dans la vue Tâches. Confirmation et dépendances terminées requises; aucun agent n’est démarré; historique d’exécution conservé.
- Première suite : échec du test de filtrage (token GitHub factice), puis échec du contrôle d’identifiant projet; corrections appliquées. Vérification finale : 92 tests passent avec Python 3.12, `node --check` passe, aucun appel réseau de fournisseur.
- Phase 2 laissée `needs_review`, non modifiée. Changements non commités et non poussés.


## 2026-10-01 — Finalisation du Skill Builder MVP

- Relecture de la spécification : la sandbox avancée est classée post-MVP; le critère de sécurité est de ne jamais exécuter du code sans elle. Windows Sandbox est désactivé, Docker/Podman absents; WSL seul n’offre pas l’isolation requise. Aucune installation système ni exécution de code de skill effectuée.
- Audit de la vue Skills : correction d’un défaut où l’inspection d’une mise à jour disponible référençait une variable non initialisée. Le diagnostic statique d’intégrité rapporte désormais proprement une altération au lieu de lever une exception.
- Tests Skill Builder : 8 réussis. Suite complète Python 3.12 : 93 réussis. Aucun test arbitraire de skill exécuté et aucun appel fournisseur.
- Le MVP local de gestion est marqué terminé; exécution de skills reste fermée en attente d’un sandbox OS validé, hors MVP. Phase 2 n’a pas été touchée. Changements locaux, non commités/non poussés.


## 2026-10-01 — Stabilisation Planner/Coder/Tester et notifications

- Le Planner doit produire des tâches réellement exécutables, sans tâches différées d’analyse qui bloquent les dépendances. La validation des nouveaux plans vérifie l’accord entre type et rôle.
- Distinction des prompts Coder et Tester; le prompt Coder décrit le JSON brut v1.1, ses clés exactes et l’interdiction des fences/prose.
- Ajout d’une désapprobation sûre pour les plans approuvés non commencés.
- Notifications du cockpit conservées 60 secondes, les nouvelles s’ajoutent sans effacer les anciennes et le texte long s’affiche sur plusieurs lignes.
- Contrôles statiques passés; aucun appel modèle ou test de génération. Le Coder réel reste à confirmer.
