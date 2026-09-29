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
