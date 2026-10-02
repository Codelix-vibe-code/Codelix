# Build Windows Vybelix

Ce packaging crée une application de bureau Windows autonome : l’interface Vybelix s’affiche dans sa propre fenêtre Edge WebView2, sans barre de titre Windows blanche, avec commandes de fenêtre intégrées, bords arrondis et icône Vybelix. Le projet choisi par l’utilisateur et ses secrets restent hors de l’installation.

## Prérequis

- Windows x64
- Python 3.12 pour construire l’application
- Connexion Internet pendant l’installation si Microsoft Edge WebView2 Runtime est absent
- Inno Setup 6 pour générer `Vybelix-Setup-0.1.0.exe`

## Construire

Depuis la racine du dépôt :

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\windows\build.ps1
```

Pour produire uniquement le dossier d’application et `Vybelix.exe`, sans compiler l’installateur :

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\windows\build.ps1 -SkipInstaller
```

Les sorties se trouvent dans `build\windows\dist-desktop\Vybelix` et `dist\Vybelix-Setup-0.1.0.exe`.

## Premier lancement

L’installateur vérifie si le runtime WebView2 est déjà présent. Sinon, il lance silencieusement le bootstrapper Microsoft inclus dans le Setup, qui télécharge et installe le runtime Evergreen. Une connexion Internet est donc requise uniquement si le runtime est absent.

Le lanceur demande le dossier du projet. S’il n’a pas de configuration Vybelix, il propose de créer `vybelix.toml` et `docs\progress\tasks.json`. Il n’embarque ni ne copie de clé API, fichier `.env`, progression, plan, sauvegarde ou contenu de projet. Fermer la fenêtre Vybelix arrête aussi le serveur local.
