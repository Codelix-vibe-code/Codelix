# Codelix --- Cahier des charges fonctionnel et technique

**Version : 1.0 --- MVP**\
**Cible prioritaire : Windows · Langage : Python 3.12.x · Interface
initiale : CLI**

## 1. Vision du produit

Codelix est un orchestrateur d'intelligences artificielles destiné à
accompagner le développement logiciel. Il répartit le travail entre
plusieurs modèles selon leur rôle, conserve un contexte compact par
projet, suit l'avancement des tâches et contrôle les modifications
proposées avant de les appliquer.

Codelix ne doit pas être un simple chat multi-modèles. Sa valeur
principale est de transformer une demande en tâches vérifiables, de
sélectionner un modèle adapté, de produire des changements structurés,
puis de vérifier réellement le résultat.

### Objectifs du MVP

-   Transformer une demande en plan de tâches hiérarchisé et
    compréhensible.
-   Affecter les tâches aux rôles IA appropriés.
-   Prendre en charge plusieurs fournisseurs de modèles via une couche
    commune.
-   Réutiliser le contexte utile du projet sans transmettre tout le
    dépôt à chaque requête.
-   Contrôler les fichiers proposés, les appliquer de manière sûre et
    garder une trace des changements.
-   Exécuter des vérifications autorisées et présenter les résultats
    réels.
-   Permettre à l'utilisateur de garder le contrôle et de valider les
    étapes sensibles.

### Hors périmètre du MVP

-   Interface graphique complète, application mobile ou service cloud.
-   Exécution autonome et illimitée de commandes shell.
-   Modifications binaires, migrations complexes, renommages et
    suppressions automatiques.
-   Collaboration multi-utilisateur en temps réel.
-   Entraînement ou hébergement de modèles.
-   Système massif d'agents, de plugins ou de workflows
    personnalisables.

## 2. Principes de conception

1.  **Contrôle humain :** aucune action risquée ou ambiguë n'est
    exécutée sans validation.
2.  **Traçabilité :** chaque tâche possède un état, un résultat et des
    preuves de vérification.
3.  **Modularité :** les fournisseurs, le routage, la planification,
    l'exécution et la vérification sont séparés.
4.  **Simplicité :** le MVP doit rester petit, compréhensible et
    extensible.
5.  **Contexte ciblé :** lire en priorité les fichiers liés à la tâche,
    plutôt que tout le dépôt.
6.  **Aucune réussite fictive :** une tâche n'est marquée terminée
    qu'après vérification des critères convenus.
7.  **Respect de l'existant :** auditer le dépôt avant toute
    modification et réutiliser ses structures pertinentes.

## 3. Environnement technique

-   Langage cible : **Python 3.12.x**.
-   Système prioritaire : Windows.
-   Interface initiale : CLI (ligne de commande).
-   Configuration locale : fichier de configuration non secret et
    variables d'environnement pour les clés API.
-   Tests : `pytest` si compatible avec le dépôt audité.
-   Gestion de versions : Git, sans écraser les modifications locales
    existantes.

Le dépôt existant doit être audité avant d'imposer sa réorganisation.
Python 3.12 reste la cible du nouveau développement, mais l'audit doit
relever toute contrainte réelle de compatibilité avant l'implémentation.

## 4. Architecture fonctionnelle

### 4.1 Modules logiques

-   **CLI :** reçoit les demandes, affiche le plan, demande les
    validations et présente les résultats.
-   **Project Context :** collecte et maintient les informations
    compactes propres à chaque projet.
-   **Planner :** transforme une demande en tâches structurées,
    dépendances et critères d'acceptation.
-   **Provider Adapter :** interface commune aux fournisseurs d'IA.
-   **Model Router :** choisit un modèle en fonction du rôle, de la
    tâche, de la configuration et de la disponibilité.
-   **Coder :** propose les modifications de code dans un format
    structuré.
-   **Execution Manager :** valide les propositions, contrôle les
    chemins et applique les modifications approuvées.
-   **Tester :** peut proposer des tests pertinents ou des fichiers de
    test.
-   **Verifier :** composant déterministe qui exécute les tests et
    commandes autorisés, collecte les résultats et vérifie les critères.
-   **Progress Tracker :** maintient l'état des tâches et un journal
    concis des opérations.

Ces modules sont des responsabilités logiques. Ils ne doivent pas
nécessairement devenir chacun un service ou un paquet indépendant dans
le MVP.

### 4.2 Cycle principal

1.  L'utilisateur formule une demande.
2.  Codelix charge le contexte résumé du projet et inspecte les fichiers
    pertinents.
3.  Le Planner propose un plan structuré avec tâches, dépendances et
    critères d'acceptation.
4.  Codelix affiche le plan et attend l'approbation de l'utilisateur.
5.  Le Router sélectionne un modèle pour chaque rôle.
6.  Le Coder produit une proposition de modifications structurée.
7.  L'Execution Manager valide la proposition et demande l'approbation
    requise.
8.  Les changements approuvés sont appliqués et consignés.
9.  Le Verifier exécute les vérifications autorisées.
10. En cas d'échec, le Coder reçoit les erreurs utiles et propose une
    correction, dans la limite définie.
11. Codelix met à jour l'avancement et présente un rapport avec les
    preuves disponibles.

## 5. Rôles IA et vérification

  -----------------------------------------------------------------------
  Rôle                    Responsabilité          Limites
  ----------------------- ----------------------- -----------------------
  Planner                 Décomposer la demande,  Ne modifie pas les
                          définir dépendances et  fichiers
                          critères

  Coder                   Produire les            Ne peut pas appliquer
                          changements de code et  directement ses propres
                          corriger les échecs     sorties

  Tester                  Suggérer des tests et,  Ne certifie pas
                          si approuvé, produire   lui-même la réussite
                          des fichiers de test

  Verifier                Exécuter les commandes  Code déterministe, pas
                          permises et relever les un modèle IA
                          résultats
  -----------------------------------------------------------------------

Le rôle de correction n'est pas un agent distinct dans le MVP : le Coder
corrige les problèmes à partir des résultats du Verifier. Les sorties
d'un modèle restent des propositions, jamais des preuves d'exécution.

## 6. Fournisseurs et routage des modèles

### 6.1 Fournisseurs envisagés

Le système doit pouvoir évoluer vers les fournisseurs suivants : -
NVIDIA (NVIDIA Build / API disponible selon le compte) - Google Gemini -
DeepSeek - Qwen - Groq

Le MVP doit commencer avec **un ou deux fournisseurs réellement
testés**, puis en ajouter d'autres progressivement. La prise en charge
de chaque fournisseur doit être confirmée à partir de sa documentation
officielle et d'un test d'intégration. Ne pas supposer que toutes les
API sont compatibles avec le même format OpenAI.

### 6.2 Interface commune

Chaque adaptateur expose une opération conceptuelle équivalente à :

`complete(messages, model, options=None)`

L'adaptateur traduit les requêtes et réponses selon les spécificités du
fournisseur. Les URL de base, identifiants de modèles, paramètres et
limites doivent être configurables, et non codés en dur.

### 6.3 Routage

Une configuration associe à chaque rôle ou catégorie de tâche une liste
ordonnée de modèles candidats. Exemple conceptuel : - planification :
modèle candidat A, puis modèle B ; - génération de code : modèle
candidat B, puis modèle A ; - analyse légère : modèle candidat A.

Ces choix sont configurables et ne constituent pas des modèles imposés.
Le routeur doit tenir compte de la disponibilité connue, des erreurs et
des limites configurées. Le MVP ne doit pas prétendre optimiser
automatiquement le coût ou la qualité sans données mesurées.

### 6.4 Gestion des erreurs et quotas

-   **HTTP 429 / quota ou limite de débit :** passer au prochain modèle
    configuré, si disponible.
-   **Timeout ou erreur serveur 5xx :** effectuer au plus une nouvelle
    tentative, puis essayer le prochain candidat.
-   **Erreur 401 / authentification :** ne pas répéter inutilement ;
    afficher un message clair de configuration.
-   **Erreur 403 / accès refusé :** signaler le problème et arrêter la tâche concernée.
-   **Erreur 404 / ressource ou modèle introuvable :** essayer un autre modèle configuré si possible.
-   **Erreur réseau :** effectuer au plus une nouvelle tentative, puis appliquer la stratégie de fallback.
-   **Réponse invalide ou JSON incorrect :** demander une réparation
    structurée avec un nombre limité de tentatives, puis arrêter la
    tâche en `needs_review`.
-   **Aucun modèle disponible :** conserver la tâche en attente ou
    bloquée, sans perdre son état.

Les erreurs, fournisseurs sollicités et changements de modèle sont
consignés sans exposer les clés API.

## 7. Contrats de données des modèles

Toutes les réponses utilisées par le système doivent respecter un schéma
JSON documenté et être validées avant usage. Le texte libre peut être
inclus dans des champs prévus à cet effet, mais ne remplace jamais le
contrat.

### 7.1 Sortie du Planner

Le Planner retourne un objet JSON contenant au minimum : -
`schema_version` - `project_id` - `request_summary` - `affected_paths` - `tasks`

Chaque tâche contient : - `id` : identifiant stable et unique -
`parent_id` : identifiant parent ou `null` - `title` - `description` -
`type` : par exemple `analysis`, `code`, `test`, `documentation` -
`role` : rôle IA prévu - `priority` - `dependencies` : liste
d'identifiants - `acceptance_criteria` : liste de critères observables -
`verification_strategy`

Le système valide les identifiants, les dépendances, les champs
obligatoires et l'absence de dépendances circulaires. Le Planner ne doit
pas créer une quantité excessive de tâches : le plan doit rester
proportionné au MVP et à la demande.

### 7.2 Sortie du Coder

Le Coder retourne un objet JSON strict contenant : - `schema_version` -
`task_id` - `summary` - `files` - `notes` - `verification_hints`

Chaque entrée de `files` contient : - `path` : chemin relatif depuis la
racine du projet - `operation` : `write` pour le MVP - `content` :
contenu intégral du fichier proposé

Le Coder ne renvoie pas des instructions shell à exécuter
automatiquement. Les propositions en texte libre, les chemins absolus,
les opérations non prévues ou les réponses ne respectant pas le schéma
sont rejetés ou placés en revue.

Pour limiter l'ambiguïté, le MVP privilégie le contenu complet des
petits fichiers. Les grands fichiers pourront utiliser un mécanisme de
diff dans une phase ultérieure, après définition et tests de son
contrat.

### 7.3 Sortie du Tester

Le Tester peut fournir une proposition de tests structurée : objectif,
fichiers de test proposés, commandes de vérification suggérées et
critères associés. Toute commande doit être validée par le Verifier
selon une liste autorisée ; elle n'est jamais exécutée simplement parce
qu'un modèle l'a demandée.

## 8. Exécution contrôlée et sécurité

L'Execution Manager est le seul composant autorisé à appliquer les
changements proposés par le Coder.

### Contrôles obligatoires

-   Valider le JSON et la version du schéma.
-   Vérifier que le `task_id` correspond à la tâche active.
-   N'accepter que des chemins relatifs normalisés.
-   Bloquer les chemins absolus, les traversées de répertoires (`..`),
    les sorties de la racine du projet et les échappements via liens
    symboliques.
-   Bloquer les fichiers secrets, les fichiers exclus et les zones
    protégées configurées.
-   Détecter si un fichier a changé depuis son inspection ou sa
    proposition ; dans ce cas, interrompre l'application et demander une
    nouvelle analyse.
-   Afficher un aperçu des fichiers concernés avant application lorsque
    la validation utilisateur est requise.
-   Créer ou vérifier l'existence d'un point de retour avant écriture.
-   Conserver un résultat de l'application : fichiers réellement écrits,
    refusés ou ignorés.

### Environnement d'exécution

Utiliser un bac à sable réel lorsqu'il est disponible et vérifié. Sinon,
indiquer explicitement que l'exécution n'est pas isolée et appliquer une
liste stricte de commandes permises. Ne jamais présenter une exécution
locale ordinaire comme un bac à sable sécurisé.

Les commandes shell, scripts et opérations proposées par les modèles ne
sont jamais exécutés sans validation du Verifier et des règles de
sécurité. Les suppressions, renommages, modifications hors racine et
opérations destructrices sont exclues du MVP ou exigent une approbation
explicite distincte.

### Gestion des secrets

-   Stocker les clés API dans des variables d'environnement ou un
    mécanisme local adapté.
-   Garder les fichiers `.env` hors de Git.
-   Fournir un `.env.example` sans valeur secrète.
-   Masquer les secrets dans les journaux, rapports et contextes envoyés
    aux modèles.
-   Ne jamais intégrer les clés API dans le code, les prompts ou les
    fichiers de progression.

## 9. Vérification, correction et arrêt

Le Verifier exécute uniquement des commandes préalablement autorisées et
adaptées au projet : par exemple, tests ciblés, vérification de syntaxe
ou analyse statique si configurée.

Pour chaque vérification, conserver : - commande autorisée exécutée ; -
code de retour ; - résultat synthétique ; - erreurs utiles ; - heure ou
identifiant d'exécution ; - critères d'acceptation concernés.

### Boucle de correction

1.  Le Verifier détecte un échec.
2.  Codelix transmet au Coder le message d'erreur pertinent et le
    contexte minimal nécessaire.
3.  Le Coder retourne une nouvelle proposition structurée.
4.  L'Execution Manager revalide la proposition et demande l'approbation
    requise.
5.  Le Verifier relance les vérifications ciblées.

**Limite par défaut : deux tentatives de correction par tâche.** Après
cette limite, ou si l'échec reste ambigu, la tâche passe en
`needs_review` ou `blocked`. Cette limite doit être configurable, mais
ne doit pas être augmentée automatiquement.

Une tâche ne passe à `done` que lorsque ses critères vérifiables sont
satisfaits. Si une vérification n'a pas pu être exécutée, le rapport
doit le dire et la tâche ne doit pas être présentée comme entièrement
vérifiée.

## 10. Contexte et mémoire par projet

Pour réduire les coûts et éviter de réanalyser le dépôt à chaque
session, Codelix maintient un contexte concis par projet.

Il peut contenir : - objectif et description du projet ; - langage,
framework et commandes confirmés ; - architecture connue et points
d'entrée ; - conventions et décisions validées ; - état des tâches ; -
fichiers pertinents et résumés ; - problèmes ouverts et prochaines
étapes.

### Règles

-   Lire d'abord le résumé et les fichiers directement liés à la tâche.
-   Inspecter davantage uniquement si nécessaire.
-   Réutiliser les connaissances vérifiées et distinguer les faits des
    hypothèses.
-   Signaler les informations potentiellement obsolètes et les
    actualiser après des changements pertinents.
-   Produire un résumé de session compact plutôt que transmettre tout
    l'historique.
-   Ne jamais enregistrer de secrets dans la mémoire du projet.
-   Ne pas supposer qu'un résumé remplace la vérification du contenu
    réel des fichiers lorsque la tâche dépend de leur état actuel.

Cette approche vise la continuité par projet et l'économie de tokens, sans faire de la mémoire une source de vérité sur le code.

## 11. Suivi de progression --- source unique de vérité

Éviter les doublons entre plusieurs documents et la création d'un
fichier pour chaque tâche ou session. Le suivi structuré des tâches doit
avoir **une seule source de vérité**, par exemple
`docs/progress/tasks.json`, sauf si le dépôt possède déjà un système
équivalent pertinent.

Chaque tâche suit l'un des états : - `todo` - `in_progress` -
`blocked` - `needs_review` - `done` - `interrupted` - `cancelled`

Les données de progression comprennent au minimum l'identifiant, le
titre, l'état, les dépendances, les critères, les tentatives, les
fichiers modifiés, les vérifications et le dernier résultat.

Documents lisibles complémentaires, mis à jour à partir de cette source :

- `PROJECT_STATUS.md` : vue d'ensemble courte.
- `sessions.md` : résumés compacts des sessions.
- `README.md` : installation, configuration et utilisation.

Si le dépôt dispose déjà d'une organisation de suivi satisfaisante, la
réutiliser au lieu de créer une seconde structure. Mettre à jour la
progression après chaque tâche ou événement significatif, en ne
déclarant que les actions réellement réalisées.

## 12. Configuration par défaut

Ces valeurs constituent des paramètres initiaux du MVP. Elles doivent
être configurables, tout en conservant des limites de sécurité
raisonnables.

-   **Commandes de vérification :** après l’audit, proposer les commandes adaptées au projet et expliquer en français simple ce que chacune va faire. Ne lancer que les commandes approuvées explicitement par l’utilisateur. Le Verifier contrôle les arguments et les chemins des fichiers transmis à `py_compile`.
-   **Délai maximum par appel de modèle :** 300 secondes.
-   **Taille maximale d'un fichier transmis à un modèle :** environ 200
    Ko. Au-delà, Codelix doit sélectionner les extraits pertinents ou
    demander une stratégie adaptée, sans tronquer silencieusement le
    contenu requis.
-   **Nombre maximal de tentatives de correction :** 2 par tâche.
-   **Nouvelle tentative pour timeout, erreur réseau ou 5xx :** une
    seule, avant fallback vers le prochain modèle configuré.
-   **Encodage des fichiers texte :** UTF-8.
-   **Environnement Python :** `venv` local au projet lorsque possible.
-   **Chemins :** utiliser `pathlib` pour garantir la compatibilité Windows.
-   **Sécurité subprocess :** interdire l'utilisation de `shell=True`.

Ces paramètres doivent être centralisés dans la configuration plutôt que
dispersés dans le code. Une configuration invalide doit produire un
message explicite et empêcher l'exécution concernée.

## 13. Interface CLI du MVP

La CLI doit permettre de : - créer ou ouvrir un projet ; - afficher le
statut et les tâches ; - soumettre une demande ; - consulter et
approuver ou refuser un plan ; - afficher la proposition de fichiers
avant application ; - lancer les vérifications autorisées ; - consulter
les résultats, erreurs et changements de modèle ; - reprendre une tâche
interrompue ou bloquée.

Les commandes et leur syntaxe exacte seront proposées après audit du
dépôt, puis validées avant implémentation.

## 14. Création du dépôt et phases de réalisation

### Création du dépôt

Le projet Codelix doit être créé dans un nouveau dépôt, en parallèle de tout dépôt existant. Utiliser le plugin de création de dépôt disponible dans l’environnement. Le dépôt existant ne doit pas être modifié. Si le plugin nécessaire n’est pas disponible ou si la création exige une information manquante, le signaler et attendre les instructions de l’utilisateur.

Avant la première modification du nouveau dépôt, établir un point de retour Git. Ne jamais inclure dans ce point de retour des fichiers ou modifications provenant d’un dépôt existant sans autorisation explicite.

### Règle de validation entre les phases

À la fin de chaque phase, remettre un rapport en français simple qui décrit le travail réalisé et les vérifications réellement exécutées, puis s’arrêter. Attendre l’accord explicite de l’utilisateur avant de commencer la phase suivante. Ne pas poursuivre automatiquement, même si la phase suivante semble évidente.

### Phases de réalisation

### Phase 0 --- Audit uniquement du nouveau dépôt

-   Examiner le dépôt et les fichiers existants.
-   Identifier la structure, les technologies, les points d'entrée, les
    tests et les changements locaux.
-   Relever les éléments réutilisables, les risques et les blocages.
-   Comparer l'existant à ce cahier des charges.
-   Proposer une architecture minimale et un plan de tâches réaliste.

**Aucun code ne doit être modifié pendant cette phase. Aucune dépendance
ne doit être installée.**

### Phase 1 --- Fondations

Après validation explicite de l'audit : - mettre en place les contrats
JSON ; - définir la configuration ; - créer ou adapter le suivi des
tâches ; - ajouter les tests des schémas et validations.

### Phase 2 --- Fournisseurs et routage

Après validation de la phase précédente : - implémenter les adaptateurs
des un ou deux fournisseurs retenus ; - vérifier les formats réellement
pris en charge ; - implémenter le routage, le fallback et la gestion des
erreurs ; - tester avec des appels réels uniquement si les clés et
quotas sont configurés.

### Phase 3 --- Exécution contrôlée

Avant toute écriture, créer un point de retour (commit Git, tag ou copie de sauvegarde selon le contexte du dépôt).

Après validation : - implémenter le contrôle des chemins et fichiers ; -
afficher les propositions ; - appliquer les modifications autorisées ; -
journaliser les changements et gérer les conflits de fichiers.

### Phase 4 --- Boucle de vérification

Après validation : - ajouter le Verifier déterministe ; - exécuter les
tests autorisés ; - transmettre les erreurs utiles au Coder ; - limiter
et tracer les corrections.

### Phase 5 --- Expérience CLI et stabilisation

Après validation : - finaliser les commandes CLI ; - documenter
installation et configuration ; - effectuer les tests de bout en bout
; - corriger les défauts observés et préparer une démonstration
reproductible.

Chaque phase est limitée à un périmètre explicite. Ne pas lancer
automatiquement toutes les tâches ou toutes les phases à la suite.

## 15. Critères d'acceptation du MVP

Le MVP est acceptable lorsque : - une demande produit un plan JSON
valide avec tâches et dépendances ; - l'utilisateur peut examiner et
approuver le plan ; - au moins un fournisseur est intégré et testé, avec
une conception permettant d'en ajouter d'autres ; - le routeur traite
les erreurs prévues sans perdre l'état ; - le Coder produit une sortie
structurée validée ; - les chemins non sûrs ou hors projet sont rejetés
; - les modifications approuvées sont appliquées et consignées ; - le
Verifier exécute une commande autorisée et rapporte son code de retour
; - une correction est possible dans la limite définie ; - les tâches
non vérifiées ne sont pas marquées `done` ; - la progression peut être
reprise après interruption ; - les secrets ne sont pas exposés dans les
fichiers suivis ou les journaux ; - les instructions d'installation et
d'utilisation sont documentées.

## 16. Risques et décisions à confirmer

-   Compatibilité réelle des API et modèles des fournisseurs retenus.
-   Disponibilité d'un environnement d'exécution isolé sur la machine
    cible.
-   Commandes de tests permises selon le dépôt audité.
-   Taille maximale raisonnable des fichiers transmis aux modèles.
-   Politique d'approbation des modifications selon les capacités de
    revue disponibles.

Ces points doivent être consignés comme décisions ou blocages, et non
résolus par des suppositions.

## 17. Instruction initiale à donner à Codex

> Tu travailles sur **Codelix**, un orchestrateur multi-modèles d'IA pour le développement logiciel. Crée d’abord un nouveau dépôt en parallèle de tout dépôt existant, en utilisant le plugin de création de dépôt disponible. Ne modifie pas le dépôt existant. Si le plugin requis n’est pas disponible ou qu’une information indispensable manque, explique le blocage et attends mes instructions.
>
> Réalise uniquement la Phase 0 : audit du nouveau dépôt et préparation de l’architecture. Examine les fichiers, la structure, les technologies, les points d’entrée, les tests, la configuration et les changements présents. Identifie les éléments réutilisables, les écarts avec ce cahier des charges, les risques et les blocages. La cible est Python 3.12.x sous Windows ; relève les contraintes réelles sans modifier le code ni installer de dépendances.
>
> À la fin, fournis en français simple :
> 1. l’état factuel du dépôt ;
> 2. les composants et fichiers réutilisables ;
> 3. les écarts et risques ;
> 4. une architecture minimale proposée ;
> 5. un plan de tâches avec dépendances et critères d’acceptation ;
> 6. les décisions qui nécessitent ma réponse ;
> 7. les commandes de vérification proposées, avec une explication simple de ce que chacune fera.
>
> Ne lance aucune commande de vérification avant mon approbation explicite. Ne commence aucune implémentation, ne modifie aucun fichier, n’installe aucune dépendance et ne lance pas automatiquement la Phase 1. Préserve le dépôt existant. N’affirme pas qu’une vérification a réussi si elle n’a pas réellement été exécutée. Après le rapport d’audit, arrête-toi et attends mon accord explicite avant la phase suivante.
