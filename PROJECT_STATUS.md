# État du projet Codelix

- **Phase courante :** Phases 0, 1, 3, 4 et 5 terminées ; Phase 2 en revue avant appel fournisseur réel.
- **Dépôt :** [Codelix-vibe-code/Codelix](https://github.com/Codelix-vibe-code/Codelix), privé.
- **Environnement constaté :** Windows, Python 3.12.14 fourni par l’environnement Codex.
- **Progression faisant foi :** [`docs/progress/tasks.json`](docs/progress/tasks.json).
- **Vérifications :** 55 tests `unittest` réussis avec Python 3.12.14 ; `pytest` n’est pas installé. Les échanges fournisseur sont simulés ; aucun appel fournisseur réel n'a été envoyé.
- **Fournisseurs IA :** adaptateurs NVIDIA Build, Gemini et Groq intégrés. Les clés locales sont chargées depuis `.env`; les modèles restent à choisir dans `codelix.toml`.
- **Application des changements :** aperçu sans écriture, approbation explicite, contrôle des chemins et sauvegardes locales avant remplacement.
- **Vérificateur :** commandes exactes de la liste autorisée, exécutées sans shell, avec sortie, code de retour, critères, durée et masquage des secrets.
- **CLI :** `python -m codelix --help` liste `init`, `status`, `config`, `plan`, `approve-plan`, `code`, `apply` et `verify`.
