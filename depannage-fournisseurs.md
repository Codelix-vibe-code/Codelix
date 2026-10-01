# Dépannage des fournisseurs — accès API

Document de référence établi à partir de requêtes réelles courtes (aucune clé
affichée, aucun achat ni top-up effectué). Il décrit comment débloquer les
fournisseurs qui ne répondent pas encore correctement.

## État des routes (actuel)

- **Actifs** : `gemini:gemini-3.5-flash`, `nvidia:openai/gpt-oss-20b`.
- **Secours Tester** : `mistral:mistral-medium-3.5` (répond 429, à résoudre).
- **OpenRouter** : retiré jusqu'au renouvellement de la clé.
- **Groq** : bloqué par la couche de sécurité (403 / code 1010), indépendant du modèle.

## Variables d'environnement attendues (`.env`)

| Fournisseur | Variable | Format de clé constaté |
|---|---|---|
| Gemini | `GEMINI_API_KEY` | `AQ.…` (acceptée : `GET /models` → 200) |
| NVIDIA | `Nvidia_API_KEY` | `nvapi-…` (fonctionne) |
| Groq | `Groq_API_KEY` | `gsk_…` |
| OpenRouter | `Openrouter_API_KEY` | `sk-or-v1-…` |
| Mistral | `Mistral_API_KEY` | `mstrl_…` |

Les clés sont chargées depuis le `.env` à la racine du projet (près de
`vybelix.toml` / `codelix.toml`). L'interface **Paramètres → API KEYS** écrit
dans ce même `.env`. La valeur d'une clé n'est jamais affichée ni journalisée.

---

## 1. OpenRouter — HTTP 401 (clé refusée)

**Symptôme** : les modèles `:free` renvoient `401`.

**Cause** : la clé est rejetée par OpenRouter. Le top-up de 10 $ ne corrige
**pas** une clé refusée.

**À faire** :

1. Ouvrir <https://openrouter.ai/settings/keys> et créer/renouveler une clé
   (format `sk-or-v1-…`).
2. Mettre à jour le `.env` :
   ```dotenv
   Openrouter_API_KEY=sk-or-v1-...
   ```
3. Vérifier la clé :
   ```powershell
   curl -H "Authorization: Bearer sk-or-v1-..." https://openrouter.ai/api/v1/models
   ```
   Une réponse HTTP 200 confirme que la clé est acceptée.
4. Une fois la clé valide, faire un top-up unique de 10 $ pour débloquer les
   modèles `:free`, puis réintégrer les candidats :
   ```toml
   openrouter:nvidia/nemotron-3-ultra-550b-a55b:free
   openrouter:poolside/laguna-s-2.1:free
   ```

---

## 2. Mistral — HTTP 429 (quota / débit)

**Symptôme** : la clé est reconnue (`GET /models` → 200), mais la génération
renvoie `429`.

**Cause** : quota ou débit du compte dépassé, pas une erreur de clé ni d'ID.

**À faire** :

1. Ouvrir la console <https://console.mistral.ai> et consulter l'onglet
   usage/limites.
2. Attendre la fenêtre de quota, réduire le rythme des requêtes, ou passer à
   un plan supérieur.
3. Utiliser l'ID **valide** `mistral-medium-3.5` (l'ID
   `mistral-medium-3.5-128b` renvoie `400 Invalid model`).

**Vérifier la clé** :
```powershell
curl -H "Authorization: Bearer mstrl-..." https://api.mistral.ai/v1/models
```

---

## 3. Groq — HTTP 403 / code 1010 (blocage sécurité)

**Symptôme** : `403` avec code `1010`, observé aussi bien pour `openai/gpt-oss-20b`
que pour `moonshotai/kimi-k2-instruct`.

**Cause** : blocage par la couche de sécurité du fournisseur (signature de
type Cloudflare, code 1010). Ce n'est **pas** une réponse d'authentification
JSON : on ne peut pas en conclure que la clé est invalide, ni que le modèle
est en cause.

**À faire** :

1. Vérifier la clé indépendamment :
   ```powershell
   curl -H "Authorization: Bearer gsk-..." https://api.groq.com/openai/v1/models
   ```
   HTTP 200 = la clé est valide.
2. Contacter le support Groq (<https://console.groq.com>) en mentionnant le
   code `1010`.
3. Réessayer depuis un autre réseau / une autre IP.
4. Vérifier le statut du compte dans <https://console.groq.com/settings>.

---

## Modèles à réintégrer une fois débloqués

| Fournisseur | Candidat(s) |
|---|---|
| OpenRouter | `openrouter:nvidia/nemotron-3-ultra-550b-a55b:free`, `openrouter:poolside/laguna-s-2.1:free` |
| Mistral | `mistral:mistral-medium-3.5` |
| Groq | `groq:moonshotai/kimi-k2-instruct` |

## Notes complémentaires

- **Gemini** : seul `gemini-3.5-flash` est confirmé dans `GET /models` et testé
  fonctionnel ; `gemini-3.7-flash` et `gemini-3.8-flash` ne sont pas dans la
  liste (timeout).
- **NVIDIA** : `openai/gpt-oss-20b` fonctionne mais consomme son budget de
  sortie pour raisonner ; utiliser un budget de sortie suffisant (le routeur
  injecte désormais `max_completion_tokens` pour OpenAI et `max_tokens` pour les
  autres fournisseurs compatibles).
- **Kimi (NVIDIA)** : a renvoyé `404` lors du diagnostic ; non retenu dans les
  routes.
