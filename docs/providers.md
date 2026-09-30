# Fournisseurs et routage

Vybelix charge automatiquement les affectations simples du fichier `.env`
placé près de `vybelix.toml`. Les variables déjà définies dans le processus
ont priorité. Le `.env` est ignoré par Git ; ne le partagez pas.

## Fournisseurs compatibles Chat Completions

NVIDIA Build, Groq, OpenRouter et Mistral utilisent le format Chat Completions
compatible OpenAI. Le routeur Vybelix instancie le même adaptateur Python pour
ces fournisseurs et construit `POST {base_url}/chat/completions`, avec Bearer
auth. Les réponses SSE sont lues par l'adaptateur ; le mode JSON non-streamé
reste disponible via une option explicite. OpenRouter reçoit aussi les en-têtes
optionnels d’identification `HTTP-Referer` et `X-Title`.

Endpoints configurés par défaut :
- NVIDIA : `https://integrate.api.nvidia.com/v1/chat/completions` ;
- Groq : `https://api.groq.com/openai/v1/chat/completions` ;
- OpenRouter : `https://openrouter.ai/api/v1/chat/completions` ;
- Mistral : `https://api.mistral.ai/v1/chat/completions`.

Ajouter un fournisseur ne choisit pas de modèle et ne garantit pas que le compte
peut générer avec ce modèle. Le catalogue peut répondre alors que l’inférence
est refusée, limitée ou indisponible.

- [Référence NVIDIA LLM APIs](https://docs.api.nvidia.com/nim/reference/llm-apis)
- [Référence NVIDIA chat completion](https://docs.api.nvidia.com/nim/reference/meta-llama2-70b-infer)
- [Référence Groq Chat Completions](https://console.groq.com/docs/api-reference)
- [Vue d'ensemble Groq et compatibilité](https://console.groq.com/docs/overview)

Dans `.env`, les noms de variables configurés pour ce projet sont
`Nvidia_API_KEY`, `Groq_API_KEY`, `Openrouter_API_KEY` et `Mistral_API_KEY`.
Les blocs fournisseurs correspondants sont présents dans `vybelix.toml` et
`config.example.toml`. Ajoutez vous-même les candidats au rôle voulu dans
`[models]` après avoir vérifié l’accès à l’inférence sur votre compte ; aucun
modèle par défaut n’est sélectionné automatiquement.

## Gemini

Vybelix utilise l'API REST **GenerateContent** de Gemini sur `v1beta` pour ses
requêtes textuelles sans état serveur. Les messages système passent dans
`systemInstruction`; l'historique user/assistant passe dans `contents`. La clé
est envoyée via `x-goog-api-key` et n'apparait pas dans l'URL. Le texte est lu
dans `candidates[].content.parts[].text`.

- [Référence REST GenerateContent](https://ai.google.dev/api/generate-content)
- [Guide officiel de génération de texte](https://ai.google.dev/gemini-api/docs/text-generation)
- [Documentation des clés Gemini](https://ai.google.dev/gemini-api/docs/api-key)

Référence vérifiée le 30 septembre 2026. Un appel court a renvoyé HTTP 200 et
`OK`; des essais suivants ont renvoyé HTTP 503. L'accès est donc intermittent
et dépend de la disponibilité du service/modèle.

L'adaptateur utilise uniquement la bibliothèque standard Python et n'exécute
aucun outil du fournisseur. Les contrats Planner/Coder sont validés localement
après réception du texte.

## Configurer les candidats

Dans `vybelix.toml`, définissez les clés d'environnement et les candidats par
rôle. Un candidat utilise le format `fournisseur:identifiant-du-modèle`.
Plusieurs candidats sont essayés dans l'ordre :

```toml
[providers.gemini]
base_url = "https://generativelanguage.googleapis.com/v1beta"
api_key_env = "GEMINI_API_KEY"

[models]
planner = ["gemini:gemini-2.5-flash"]
coder = ["gemini:gemini-2.5-pro", "gemini:gemini-2.5-flash"]
tester = ["gemini:gemini-2.5-flash"]
```

Les identifiants ci-dessus illustrent la syntaxe de routage ; Vybelix ne les
active pas automatiquement. Vérifiez les identifiants accessibles dans votre
compte avant de les choisir. La variable `GEMINI_API_KEY` doit être définie
dans l'environnement du processus.

## Erreurs et fallback

- HTTP 401 : signaler le problème de clé et arrêter la tâche.
- HTTP 403 : signaler l'accès refusé pour ce candidat et essayer le candidat de secours explicitement configuré.
- HTTP 404 ou 429 : essayer le candidat suivant.
- HTTP 5xx, timeout, erreur réseau ou HTTP 429 : jusqu’à deux nouveaux essais,
  espacés par un backoff exponentiel (1 s, 2 s, puis 4 s au maximum configuré)
  avec une gigue aléatoire, puis fallback. Réduisez `network_retries` à 0 pour
  désactiver ces retries. Les réponses 401/403 ne sont jamais réessayées.
- Réponse invalide : arrêter la route et laisser l'appelant placer la tâche en
  revue.

La trace du routeur comprend le fournisseur, le modèle, le statut et un message
synthétique. Elle ne contient ni clé API, ni prompt, ni réponse du modèle.

## Aperçu frontend des API Keys

La vue **Paramètres → API KEYS** ouvre une fenêtre de démonstration avec saisie
du PIN, ajout de plusieurs entrées nom/clé, remplacement et retrait. C’est pour
l’instant un aperçu frontend : le PIN et les noms vivent en mémoire de la page,
les valeurs des clés sont aussitôt jetées après validation, et rien n’est
envoyé au serveur ni écrit dans `.env`. Les entrées disparaissent au
rechargement. Le branchement au système de configuration et aux appels
fournisseurs reste à effectuer séparément.
