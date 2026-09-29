# Fournisseurs et routage

## Gemini

Codelix utilise l'API REST **Interactions** de Gemini sur l'API stable `v1`.
La documentation officielle la recommande pour les nouveaux usages agentiques ;
elle accepte une entrée textuelle, une consigne système et des réglages de
génération. La clé est envoyée dans l'en-tête `x-goog-api-key` et n'apparaît pas
dans l'URL. La réponse est lue dans les étapes `model_output` de l'interaction.

- [Vue d'ensemble des Interactions Gemini](https://ai.google.dev/gemini-api/docs/interactions-overview)
- [Référence REST de l'API Interactions](https://ai.google.dev/api/interactions-api)
- [Documentation des clés Gemini](https://ai.google.dev/gemini-api/docs/api-key)

Référence vérifiée le 29 septembre 2026.

L'adaptateur utilise uniquement la bibliothèque standard Python. Il n'exécute
aucun outil du fournisseur. Les messages sont transmis sans stockage serveur
(`store: false`). Le compte et le quota Gemini n'ont pas été testés en direct.

## Configurer les candidats

Dans `codelix.toml`, définissez les clés d'environnement et les candidats par
rôle. Un candidat utilise le format `fournisseur:identifiant-du-modèle`.
Plusieurs candidats sont essayés dans l'ordre :

```toml
[providers.gemini]
base_url = "https://generativelanguage.googleapis.com/v1"
api_key_env = "GEMINI_API_KEY"

[models]
planner = ["gemini:gemini-2.5-flash"]
coder = ["gemini:gemini-2.5-pro", "gemini:gemini-2.5-flash"]
tester = ["gemini:gemini-2.5-flash"]
```

Les identifiants ci-dessus illustrent la syntaxe de routage ; Codelix ne les
active pas automatiquement. Vérifiez les identifiants accessibles dans votre
compte avant de les choisir. La variable `GEMINI_API_KEY` doit être définie
dans l'environnement du processus.

## Erreurs et fallback

- HTTP 401 : signaler le problème de clé et arrêter la tâche.
- HTTP 403 : signaler l'accès refusé et arrêter la tâche.
- HTTP 404 ou 429 : essayer le candidat suivant.
- HTTP 5xx, timeout ou erreur réseau : un seul nouvel essai, puis fallback.
- Réponse invalide : arrêter la route et laisser l'appelant placer la tâche en
  revue.

La trace du routeur comprend le fournisseur, le modèle, le statut et un message
synthétique. Elle ne contient ni clé API, ni prompt, ni réponse du modèle.
