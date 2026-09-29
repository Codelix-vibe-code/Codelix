# Codelix

Codelix est un orchestrateur multi-modèles d'IA destiné à accompagner le
développement logiciel. Le dépôt commence par les fondations du MVP : contrats
JSON validés, configuration locale et suivi vérifiable des tâches.

## Environnement

- Python 3.12.x
- Windows en priorité
- Aucune dépendance d'exécution n'est nécessaire pour les fondations actuelles.

Créez un environnement virtuel avec `python -m venv .venv`, puis activez-le
avec `.\.venv\Scripts\Activate.ps1` dans PowerShell. Copiez
`config.example.toml` vers `codelix.toml` et ne placez jamais de clé API dans un
fichier suivi par Git. Les clés seront fournies par variables d'environnement.

## Vérifications

Les tests reposent sur la bibliothèque standard :

```powershell
python -m unittest discover -s tests -v
```

La suite est également compatible avec `pytest` lorsqu'il est installé.

Les adaptateurs Gemini, NVIDIA Build et Groq sont décrits dans
[`docs/providers.md`](docs/providers.md). Aucun modèle n'est activé par défaut ;
les identifiants et l'ordre des candidats sont choisis dans `codelix.toml`.

## CLI

Après installation (`python -m pip install -e .`) :

```powershell
codelix init .
codelix config
codelix status
codelix plan "Ajouter une page de connexion"
codelix approve-plan
codelix code --task-id TACHE
codelix apply .codelix-cache/proposals/ID.json --task-id TACHE
codelix verify --task-id TACHE --command "python -m unittest discover -s tests -v"
```

`init` ne remplace jamais les fichiers existants. `verify` n'exécute que la
ligne exacte inscrite dans `verifier.allowed_commands`. `apply` affiche d'abord
les fichiers et demande une confirmation interactive avant toute écriture.
Ajoutez uniquement des commandes de vérification adaptées et approuvées dans
`codelix.toml`.

`plan` et `code` envoient une requête au fournisseur seulement quand vous lancez
ces commandes et après avoir configuré des candidats dans `[models]`. `plan`
enregistre un brouillon; `approve-plan` affiche les tâches et critères puis
demande une confirmation. `code` valide le JSON retourné et n'écrit aucun fichier.
