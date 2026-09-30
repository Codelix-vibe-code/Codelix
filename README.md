# Vybelix

Vybelix est un orchestrateur multi-modèles d'IA destiné à accompagner le
développement logiciel. Le dépôt commence par les fondations du MVP : contrats
JSON validés, configuration locale et suivi vérifiable des tâches.

## Environnement

- Python 3.12.x
- Windows en priorité
- Aucune dépendance d'exécution n'est nécessaire pour les fondations actuelles.

Créez un environnement virtuel avec `python -m venv .venv`, puis activez-le
avec `.\.venv\Scripts\Activate.ps1` dans PowerShell. Copiez
`config.example.toml` vers `vybelix.toml` et ne placez jamais de clé API dans un
fichier suivi par Git. Les clés seront fournies par variables d'environnement.

## Vérifications

Les tests reposent sur la bibliothèque standard :

```powershell
python -m unittest discover -s tests -v
```

La suite est également compatible avec `pytest` lorsqu'il est installé.

Les adaptateurs Gemini, NVIDIA Build et Groq sont décrits dans
[`docs/providers.md`](docs/providers.md). Aucun modèle n'est activé par défaut ;
les identifiants et l'ordre des candidats sont choisis dans `vybelix.toml`.

## CLI

Après installation (`python -m pip install -e .`) :

```powershell
vybelix init .
vybelix config
vybelix status
vybelix plan "Ajouter une page de connexion"
vybelix approve-plan
vybelix code --task-id TACHE
vybelix apply .vybelix-cache/proposals/ID.json --task-id TACHE
vybelix verify --task-id TACHE --command "python -m unittest discover -s tests -v"
```

`init` ne remplace jamais les fichiers existants. `verify` n'exécute que la
ligne exacte inscrite dans `verifier.allowed_commands`. `apply` affiche d'abord
les fichiers et demande une confirmation interactive avant toute écriture.
Ajoutez uniquement des commandes de vérification adaptées et approuvées dans
`vybelix.toml`.

`plan` et `code` envoient une requête au fournisseur seulement quand vous lancez
ces commandes et après avoir configuré des candidats dans `[models]`. `plan`
enregistre un brouillon; `approve-plan` affiche les tâches et critères puis
demande une confirmation. `code` valide le JSON retourné et n'écrit aucun fichier.


## Interface graphique locale

Depuis la racine du projet, lancez :

```powershell
python -m vybelix ui
```

Vybelix ouvre son interface sur `127.0.0.1`. Le tableau de bord lit l’état réel du
projet. Planner, Coder et Tester ne sont appelés qu’après une action explicite.
Un plan doit être approuvé avant l’ajout des tâches ; les propositions sont
présentées en diff et chaque application demande une approbation distincte.
L’onglet Verification n’exécute que les commandes de la liste autorisée, après
confirmation. Files masque les secrets et n’ouvre que des fichiers texte UTF-8
limités en taille. Git est consultatif : l’interface ne crée pas de commit ni de
branche. Aucune clé API n’est affichée. Arrêtez le serveur avec `Ctrl+C`.
