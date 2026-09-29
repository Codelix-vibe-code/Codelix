# État du projet Codelix

- **Phase courante :** Phase 2 — fournisseurs Gemini, NVIDIA Build et Groq ; revue en attente pour l'appel réel.
- **Dépôt :** [Codelix-vibe-code/Codelix](https://github.com/Codelix-vibe-code/Codelix), privé.
- **Environnement constaté :** Windows, Python 3.12.14 fourni par l’environnement Codex.
- **Progression faisant foi :** [`docs/progress/tasks.json`](docs/progress/tasks.json).
- **Vérifications :** 44 tests `unittest` réussis avec Python 3.12.14 ; `pytest` n’est pas installé. Les échanges fournisseur sont simulés ; aucun appel fournisseur réel n'a été envoyé.
- **Fournisseurs IA :** adaptateurs NVIDIA Build, Gemini et Groq intégrés. Les clés locales sont chargées depuis `.env`; les modèles restent à choisir dans `codelix.toml`.
