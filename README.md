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

L'adaptateur Gemini et le format de configuration sont décrits dans
[`docs/providers.md`](docs/providers.md). Aucun modèle n'est activé par défaut ;
les identifiants et l'ordre des candidats sont choisis dans `codelix.toml`.
