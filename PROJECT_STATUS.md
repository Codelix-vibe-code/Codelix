# État du projet Codelix

- **Phase courante :** Phase 6 — UI-01 à UI-10 implémentées : dashboard, chat Planner, tâches, agents/modèles, Files/Changes, vérification, Git/History et Settings. UI-10 couvre la finition visuelle et l’accessibilité. La Phase 2 reste en revue : aucune génération fournisseur réussie n’est confirmée.
- **Dépôt :** [Codelix-vibe-code/Codelix](https://github.com/Codelix-vibe-code/Codelix), privé.
- **Environnement constaté :** Windows, Python 3.12.14 fourni par l’environnement Codex.
- **Progression faisant foi :** [`docs/progress/tasks.json`](docs/progress/tasks.json).
- **Vérifications locales :** les résultats historiques sont consignés dans `docs/progress/tasks.json`. Aucun test n’a été ajouté ou lancé pendant la finition UI de cette session.
- **Fournisseurs :** Gemini GET modèles HTTP 200 et modèles configurés listés, mais génération minimale HTTP 503 ; NVIDIA GET modèles HTTP 200, mais POST de génération expiré après environ 300 s ; Groq GET modèles HTTP 403. Aucun appel API IA ne fait partie de UI-01.
- **Interface UI :** interface locale via `python -m codelix ui`, limitée à `127.0.0.1`. Les vues lisent les données réelles ; Planner/Coder/Tester ne sont appelés qu’après action explicite. Approbation du plan avant ajout des tâches, diff et confirmation avant application, vérificateur limité à la liste autorisée. Aucun commit automatique.
- **Sécurité :** `.env` reste ignoré par Git ; valeurs secrètes absentes des réponses de l’interface. Les propositions restent sous contrôle du moteur et de l’approbation utilisateur.
- **CLI :** `python -m codelix --help` liste désormais neuf commandes, dont `ui`.
