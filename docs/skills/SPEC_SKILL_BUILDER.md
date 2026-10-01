# Cahier des charges — Codelix Skill Builder

**Version : 1.0**
**Projet : Codelix**
**Module : Skill Builder**
**Statut : Post-MVP / Extension architecturale**

---

## 1. Vision

Le **Skill Builder** est le système d’extension de Codelix.

Son objectif est de permettre à Codelix de **créer, installer, configurer, tester, versionner et utiliser des skills spécialisés**, sans modifier inutilement le cœur de Codelix.

Un skill représente une **capacité spécialisée** que Codelix peut utiliser lorsqu’une tâche le nécessite.

Exemples :

- recherche Web ;
- recherche GitHub ;
- analyse de documentation ;
- Agent-Reach ;
- analyse de dépendances ;
- génération de documentation ;
- analyse de logs ;
- intégration avec une API ;
- outils de développement spécialisés.

Le Skill Builder ne doit cependant pas devenir un système d’agents autonome et incontrôlé.

### Principe fondamental

> **Le Skill Builder étend les capacités de Codelix sans retirer à l’utilisateur le contrôle des actions sensibles.**

---

## 2. Objectifs

Le Skill Builder doit permettre de :

1. découvrir des skills ;
2. créer un skill ;
3. installer un skill ;
4. désinstaller un skill ;
5. activer ou désactiver un skill ;
6. configurer un skill ;
7. vérifier son état ;
8. tester ses capacités ;
9. mettre à jour un skill ;
10. gérer ses versions ;
11. consulter ses permissions ;
12. empêcher un skill non autorisé d’effectuer des actions sensibles ;
13. permettre à Planner, Coder et Tester d’utiliser les skills appropriés ;
14. conserver une trace des opérations.

---

## 3. Définition d’un Skill

Un skill est un **module de capacité déclaratif**.

Il ne doit pas simplement être un prompt.

Un skill peut contenir :

```text
skill/
├── SKILL.md
├── skill.json
├── config.schema.json
├── capabilities.json
├── instructions/
├── adapters/
├── tests/
└── resources/
```

Tous ces éléments ne sont pas obligatoires.

Le minimum requis est :

```text
SKILL.md
skill.json
capabilities.json
```

---

## 4. Manifeste `skill.json`

Chaque skill doit posséder un manifeste.

Exemple :

```json
{
  "schema_version": "1.0",
  "id": "agent-reach",
  "name": "Agent-Reach",
  "version": "1.0.0",
  "description": "Accès contrôlé à différentes sources externes",
  "author": "...",
  "license": "MIT",
  "entrypoint": "adapters/main.py",
  "capabilities": [
    "web.search",
    "github.search",
    "youtube.search"
  ]
}
```

Le manifeste doit permettre à Codelix de déterminer :

- l’identité du skill ;
- sa version ;
- son auteur ;
- sa licence ;
- sa description ;
- son point d’entrée ;
- ses capacités ;
- ses dépendances ;
- ses permissions ;
- sa configuration nécessaire.

---

## 5. Capacités

Chaque skill doit déclarer explicitement ce qu’il sait faire.

Exemple :

```json
{
  "capabilities": [
    {
      "id": "web.search",
      "description": "Rechercher des informations sur le Web",
      "risk": "low"
    },
    {
      "id": "github.search",
      "description": "Rechercher dans GitHub",
      "risk": "low"
    }
  ]
}
```

Codelix ne doit **jamais déduire une permission simplement à partir du code du skill**.

Les capacités doivent être déclarées et validées.

---

## 6. Permissions

Les skills doivent posséder un système de permissions.

Exemples :

```text
network.read
network.write
filesystem.read
filesystem.write
process.execute
credentials.read
browser.session
```

Chaque permission possède un niveau de risque.

### Niveau 0 — Lecture locale

Exemples :

```text
filesystem.read
```

### Niveau 1 — Réseau

```text
network.read
```

### Niveau 2 — Écriture

```text
filesystem.write
```

### Niveau 3 — Exécution

```text
process.execute
```

### Niveau 4 — Secrets / session

```text
credentials.read
browser.session
```

Les permissions dangereuses doivent être **refusées par défaut**.

---

## 7. Principe du moindre privilège

Un skill ne reçoit que les permissions nécessaires à ses capacités.

Exemple :

Un skill de recherche Web peut avoir :

```text
network.read
```

mais ne doit pas automatiquement obtenir :

```text
filesystem.write
process.execute
credentials.read
```

Une demande de permission supplémentaire doit être explicitement déclarée et soumise au système de validation de Codelix.

---

## 8. Skill Builder

Le Skill Builder doit permettre de créer un skill à partir de plusieurs méthodes.

### 8.1 Création manuelle

L’utilisateur peut créer un skill en renseignant :

- nom ;
- identifiant ;
- description ;
- auteur ;
- version ;
- licence ;
- capacités ;
- permissions ;
- dépendances ;
- configuration ;
- instructions ;
- tests.

---

### 8.2 Génération assistée par IA

L’utilisateur peut demander à Codelix :

> « Crée un skill capable d’analyser les logs Python. »

Le modèle peut alors proposer :

```text
Skill
├── manifeste
├── capacités
├── permissions
├── instructions
├── structure
└── tests
```

Mais la génération par IA reste une **proposition**.

Codelix ne doit pas installer ou activer automatiquement le skill sans validation utilisateur.

---

## 9. Cycle de vie d’un Skill

Chaque skill doit suivre un cycle de vie clair :

```text
DRAFT
  ↓
VALIDATING
  ↓
VALIDATED
  ↓
INSTALLED
  ↓
DISABLED / ENABLED
  ↓
UPDATED
  ↓
UNINSTALLED
```

### États

**DRAFT**

Le skill est en construction.

**VALIDATING**

Codelix analyse sa structure, ses permissions et ses dépendances.

**VALIDATED**

Le skill a passé les contrôles.

**INSTALLED**

Le skill est installé.

**ENABLED**

Le skill peut être utilisé.

**DISABLED**

Le skill reste installé mais ne peut pas être utilisé.

**UNINSTALLED**

Le skill est supprimé de l’environnement.

---

## 10. Validation automatique

Avant activation, Codelix doit vérifier :

- validité du manifeste ;
- identifiant unique ;
- version valide ;
- structure du skill ;
- présence des fichiers obligatoires ;
- capacités déclarées ;
- permissions demandées ;
- dépendances ;
- licence ;
- intégrité des fichiers ;
- tests disponibles ;
- absence de fichiers interdits ;
- absence de secrets exposés.

Un skill qui échoue à une vérification critique ne doit pas être activé.

---

## 11. Analyse de sécurité

Le Skill Builder doit analyser le contenu du skill avant son activation.

Il doit notamment rechercher :

- secrets en clair ;
- clés API ;
- mots de passe ;
- tokens ;
- accès non déclarés ;
- commandes dangereuses ;
- comportements incompatibles avec les permissions déclarées ;
- fichiers suspects ;
- dépendances non déclarées.

La validation ne doit pas être uniquement basée sur les déclarations du skill.

---

## 12. Installation

L’installation doit être contrôlée.

Exemple :

```text
Skill Builder
      ↓
Import
      ↓
Validation
      ↓
Analyse sécurité
      ↓
Présentation des permissions
      ↓
Approbation utilisateur
      ↓
Installation
      ↓
Test
      ↓
Activation
```

Un skill ne doit pas être considéré comme fiable simplement parce qu’il a été trouvé sur Internet.

---

## 13. Sources des Skills

Le Skill Builder peut permettre l'installation depuis :

- dossier local ;
- archive locale ;
- dépôt Git ;
- registre de skills ;
- dépôt GitHub ;
- source distante explicitement autorisée.

Toute source distante doit être considérée comme **non fiable par défaut** jusqu’à validation.

---

## 14. Vérification des licences

Chaque skill doit déclarer sa licence.

Exemples :

```text
MIT
Apache-2.0
BSD-3-Clause
Proprietary
Custom
Unknown
```

Un skill sans licence identifiable doit être signalé.

Codelix ne doit pas présenter un skill comme librement réutilisable lorsque sa licence ne l’autorise pas.

---

## 15. Dépendances

Un skill peut déclarer des dépendances.

Exemple :

```json
{
  "dependencies": [
    {
      "name": "yt-dlp",
      "version": ">=2026.1"
    }
  ]
}
```

Codelix doit :

1. détecter les dépendances ;
2. vérifier leur disponibilité ;
3. signaler les dépendances manquantes ;
4. vérifier les contraintes de version ;
5. éviter les installations silencieuses ;
6. demander une confirmation lorsque l'installation modifie l'environnement.

---

## 16. Configuration

Un skill peut définir un schéma de configuration :

```text
config.schema.json
```

Exemple :

```json
{
  "api_key": {
    "type": "secret",
    "required": false
  },
  "endpoint": {
    "type": "string",
    "required": true
  }
}
```

Les secrets doivent être stockés séparément du code du skill.

Ils ne doivent jamais être écrits :

- dans `skill.json` ;
- dans `SKILL.md` ;
- dans les logs ;
- dans les résultats envoyés au modèle ;
- dans Git.

---

## 17. Isolation des secrets

Le Skill Builder doit séparer :

```text
Skill
   │
   ├── code
   ├── instructions
   ├── configuration publique
   │
   └── secrets
          ↓
     stockage sécurisé
```

Un skill ne doit accéder qu'aux secrets explicitement autorisés.

---

## 18. Exécution

Un skill ne doit pas recevoir automatiquement tous les privilèges de Codelix.

Le système doit interposer un gestionnaire :

```text
Planner / Coder / Tester
          ↓
     Skill Manager
          ↓
 Permission Manager
          ↓
       Skill
```

Le Skill Manager vérifie avant chaque opération :

- skill activé ;
- capacité autorisée ;
- permission autorisée ;
- contexte valide ;
- limites d'exécution ;
- éventuelle confirmation utilisateur.

---

## 19. Interaction avec Planner

Le Planner peut demander l'utilisation d'un skill.

Exemple :

```json
{
  "skill": "agent-reach",
  "capability": "github.search",
  "input": {
    "query": "FastAPI OAuth2"
  }
}
```

Le Planner ne doit pas pouvoir contourner le Skill Manager.

---

## 20. Interaction avec Coder

Le Coder peut recevoir les résultats d'un skill.

Exemple :

```text
Recherche externe
       ↓
Résultats
       ↓
Contexte du Coder
       ↓
Proposition de modification
```

Les résultats externes doivent être considérés comme des **données non fiables**.

Ils ne doivent jamais être interprétés automatiquement comme des instructions système.

---

## 21. Interaction avec Tester

Un skill peut fournir :

- documentation ;
- exemples ;
- informations sur une erreur ;
- données nécessaires à un test.

Il ne doit pas pouvoir modifier les tests ou contourner les mécanismes de validation sans autorisation.

---

## 22. Protection contre le prompt injection

Toute donnée provenant d'un skill externe doit être marquée comme :

```text
UNTRUSTED_EXTERNAL_DATA
```

Exemple :

```text
Internet
  ↓
Skill
  ↓
Résultat externe
  ↓
Sanitisation
  ↓
UNTRUSTED_EXTERNAL_DATA
  ↓
Planner / Coder
```

Les instructions trouvées dans :

- pages Web ;
- dépôts GitHub ;
- issues ;
- README ;
- vidéos transcrites ;
- messages ;
- documents externes

ne doivent jamais avoir le même niveau de confiance que les instructions système de Codelix.

---

## 23. Agent-Reach comme premier Skill

Agent-Reach constitue un cas d'utilisation prioritaire du Skill Builder.

Il pourrait être installé sous forme de skill :

```text
skills/
└── agent-reach/
    ├── SKILL.md
    ├── skill.json
    ├── capabilities.json
    ├── config.schema.json
    └── adapters/
```

Ses capacités pourraient inclure, selon les outils effectivement disponibles :

```text
web.search
github.search
youtube.search
reddit.search
```

Le Skill Builder doit vérifier les dépendances et les outils nécessaires avant activation.

---

## 24. Interface utilisateur

Une section **Skills** doit être ajoutée à l'interface Codelix.

Exemple :

```text
┌─────────────────────────────────────────────┐
│ Skills                                      │
├─────────────────────────────────────────────┤
│                                             │
│ Agent-Reach             ● Activé            │
│ Recherche externe                           │
│                                             │
│ Capacités :                                 │
│ ✓ Web                                       │
│ ✓ GitHub                                    │
│ ✓ YouTube                                   │
│                                             │
│ Permissions :                               │
│ • network.read                              │
│                                             │
│ [Configurer] [Tester] [Désactiver]          │
│                                             │
├─────────────────────────────────────────────┤
│                                             │
│ [+ Créer un skill]  [Installer un skill]   │
└─────────────────────────────────────────────┘
```

---

## 25. Création d'un Skill dans l'UI

Assistant en plusieurs étapes :

```text
1. Identité
      ↓
2. Capacités
      ↓
3. Permissions
      ↓
4. Dépendances
      ↓
5. Configuration
      ↓
6. Génération
      ↓
7. Validation
      ↓
8. Test
      ↓
9. Approbation
      ↓
10. Activation
```

---

## 26. Skill Builder assisté par IA

L'IA peut aider à :

- proposer la structure ;
- générer le manifeste ;
- rédiger `SKILL.md` ;
- proposer les capacités ;
- proposer les permissions ;
- générer des tests ;
- détecter les problèmes ;
- proposer des améliorations.

Elle ne doit pas pouvoir :

- activer seule un skill ;
- accorder seule une permission critique ;
- récupérer seule des secrets ;
- installer silencieusement des dépendances ;
- exécuter arbitrairement du code avec des privilèges élevés.

---

## 27. Versionnement

Les skills doivent utiliser une version explicite.

Format recommandé :

```text
MAJOR.MINOR.PATCH
```

Exemple :

```text
1.0.0
1.1.0
2.0.0
```

Une modification de permission doit être considérée comme un changement important nécessitant une nouvelle validation.

---

## 28. Mise à jour

Lorsqu'une nouvelle version est disponible :

```text
Nouvelle version
      ↓
Comparaison
      ↓
Changements détectés
      ↓
Nouvelles permissions ?
      ↓
Validation
      ↓
Tests
      ↓
Approbation
      ↓
Mise à jour
```

Une mise à jour ne doit jamais modifier silencieusement les permissions accordées précédemment.

---

## 29. Désinstallation

La désinstallation doit supprimer :

- fichiers du skill ;
- configuration associée ;
- dépendances uniquement si leur suppression est sûre ;
- références dans le registre Codelix.

Les secrets associés doivent être traités séparément et supprimés conformément à la politique de stockage des secrets.

---

## 30. Registre local des Skills

Codelix doit maintenir un registre local.

Exemple :

```json
{
  "skills": [
    {
      "id": "agent-reach",
      "version": "1.0.0",
      "status": "enabled",
      "source": "github",
      "permissions": [
        "network.read"
      ]
    }
  ]
}
```

Le registre permet notamment de connaître :

- les skills installés ;
- leur version ;
- leur état ;
- leur source ;
- leurs permissions ;
- leurs dépendances ;
- leur dernier contrôle.

---

## 31. Logs et audit

Les opérations importantes doivent être journalisées :

```text
SKILL_DISCOVERED
SKILL_VALIDATED
SKILL_INSTALLED
SKILL_ENABLED
SKILL_DISABLED
SKILL_UPDATED
SKILL_UNINSTALLED
PERMISSION_REQUESTED
PERMISSION_GRANTED
PERMISSION_DENIED
SKILL_EXECUTION
SKILL_ERROR
```

Les logs ne doivent jamais contenir de secrets.

---

## 32. API interne

Le Skill Builder doit exposer une interface interne claire.

Exemple :

```text
SkillManager
├── discover()
├── inspect()
├── validate()
├── install()
├── uninstall()
├── enable()
├── disable()
├── configure()
├── test()
├── update()
├── execute()
└── list()
```

Les modules Codelix ne doivent pas manipuler directement les fichiers internes d'un skill.

---

## 33. Architecture cible

```text
                       CODELIX
                          │
                    Skill Manager
                          │
              ┌───────────┴───────────┐
              │                       │
       Permission Manager       Skill Registry
              │                       │
              └───────────┬───────────┘
                          │
                    Installed Skills
                          │
          ┌───────────────┼────────────────┐
          ▼               ▼                ▼
      Agent-Reach     GitHub Skill     Custom Skill
          │
          ▼
      External tools
```

---

## 34. Séparation du cœur Codelix

Le Skill Builder ne doit pas modifier directement :

- Planner ;
- Coder ;
- Tester ;
- Verifier ;
- Model Router ;
- Provider Adapters.

Ces composants doivent communiquer avec les skills via des interfaces définies.

Objectif :

```text
Cœur Codelix
      │
      │ interface stable
      ▼
Skill Manager
      │
      ▼
Skills
```

---

## 35. Tests obligatoires

Chaque skill doit pouvoir être testé indépendamment.

Tests minimum :

```text
✓ manifeste valide
✓ capacités valides
✓ permissions valides
✓ dépendances disponibles
✓ configuration valide
✓ exécution nominale
✓ erreur contrôlée
✓ permission refusée correctement
✓ secret non exposé
✓ timeout respecté
```

---

## 36. Gestion des erreurs

Un skill défaillant ne doit pas faire tomber Codelix.

Exemple :

```text
Skill
  ↓
Erreur
  ↓
Skill Manager
  ↓
Erreur isolée
  ↓
Codelix continue
```

Le système doit retourner une erreur structurée :

```json
{
  "status": "error",
  "skill": "agent-reach",
  "code": "DEPENDENCY_UNAVAILABLE",
  "message": "..."
}
```

---

## 37. Timeouts et limites

Chaque skill doit pouvoir être soumis à :

- timeout ;
- taille maximale de sortie ;
- nombre maximal de résultats ;
- nombre maximal d'appels ;
- limite de mémoire si applicable ;
- limite de fichiers ;
- limite réseau lorsque possible.

---

## 38. Compatibilité

Un skill doit déclarer les versions de Codelix compatibles.

Exemple :

```json
{
  "codelix": {
    "min": "1.0.0",
    "max": "2.x"
  }
}
```

Un skill incompatible doit être signalé avant activation.

---

## 39. Sécurité globale

Le Skill Builder doit respecter les principes suivants :

1. **Deny by default**
2. **Least privilege**
3. **Human approval for sensitive operations**
4. **Secrets never exposed to models**
5. **External content treated as untrusted**
6. **No arbitrary command execution**
7. **Explicit capabilities**
8. **Explicit permissions**
9. **Auditable operations**
10. **Isolation of failures**

---

## 40. Critères d'acceptation

Le Skill Builder sera considéré comme fonctionnel lorsque :

- [ ] un skill peut être créé ;
- [ ] un skill peut être importé ;
- [ ] son manifeste est validé ;
- [ ] ses permissions sont détectées ;
- [ ] ses dépendances sont vérifiées ;
- [ ] l'utilisateur peut approuver ou refuser son installation ;
- [ ] un skill peut être activé/désactivé ;
- [ ] un skill peut être testé ;
- [ ] un skill peut être configuré ;
- [ ] un skill peut être mis à jour ;
- [ ] un skill peut être supprimé ;
- [ ] les opérations sont journalisées ;
- [ ] les secrets ne sont pas exposés ;
- [ ] les données externes sont traitées comme non fiables ;
- [ ] un skill défaillant n'arrête pas Codelix ;
- [ ] Planner/Coder/Tester utilisent les skills uniquement via le Skill Manager ;
- [ ] aucune permission critique n'est accordée automatiquement.

---

## 41. MVP du Skill Builder

La première version du Skill Builder doit rester limitée.

### MVP

```text
✓ registre local
✓ skill.json
✓ SKILL.md
✓ capabilities.json
✓ installation locale
✓ validation
✓ activation/désactivation
✓ permissions
✓ configuration
✓ tests
✓ interface Skills
✓ Skill Manager
```

### Post-MVP

```text
○ génération IA
○ registre distant
○ marketplace
○ signature des skills
○ sandbox avancée
○ mises à jour automatiques
○ réputation des skills
○ dépendances complexes
○ Agent-Reach
```

---

## 42. Principe final

Le Skill Builder ne doit pas transformer Codelix en un agent qui peut installer n'importe quel outil et exécuter n'importe quelle action.

Il doit créer une **couche d'extension contrôlée** :

```text
Utilisateur
     │
     ▼
Codelix
     │
     ▼
Skill Manager
     │
     ├── validation
     ├── permissions
     ├── sécurité
     ├── audit
     └── exécution contrôlée
             │
             ▼
           Skill
```

La philosophie du système est donc :

> **Étendre les capacités de Codelix sans perdre le contrôle de Codelix.**
