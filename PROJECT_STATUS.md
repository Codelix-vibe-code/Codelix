# État du projet Vybelix

- **Dépôt :** [Vybelix/Vybelix](https://github.com/Vybelix/Vybelix), branche `main`.
- **Progression de référence :** [`docs/progress/tasks.json`](docs/progress/tasks.json), mise à jour le 2 octobre 2026.
- **Cahier des charges :** copie complète suivie dans [`docs/progress/PROJECT_BRIEF.md`](docs/progress/PROJECT_BRIEF.md); la copie source locale ignorée par Git reste conservée.
- **Phases MVP :** phases 0 à 5 terminées. Phase 2 est validée pour les fournisseurs conservés; Groq a été retiré de l’interface et des routes actives. La suite complète compte 102 tests réussis sous Python 3.12. NVIDIA GLM-5.3-Flash, Mistral Codestral et OpenRouter ont des générations réussies rapportées; Gemini a également des tests de connexion réussis rapportés, avec des erreurs intermittentes dans l’historique.
- **Cycle des agents :** Planner → Coder → Tester → Vérifier confirmé pour C1, C2 et T1. Le Vérifier se déclenche automatiquement après application d’une tâche Tester et reste relançable manuellement.
- **Fournisseurs :** routes Planner/Coder/Tester modifiables depuis Modèles ou lors de l’ajout d’une clé API. Le test NVIDIA des API Keys attend jusqu’à 200 s et laisse NVIDIA appliquer sa limite de sortie par défaut.
- **Installation :** wheel construite et installée sous Python 3.12.10 dans un venv temporaire; ressources UI, imports `vybelix`/`codelix`, commandes CLI et 102 tests vérifiés.
- **API Keys :** gestionnaire relié au `.env` local ignoré par Git. Les clés ne sont pas chiffrées sur disque; le PIN protège l’accès à l’interface uniquement.
- **Synchronisation :** les changements d’interface, de workflow, de fournisseurs et de suivi sont préparés pour publication sur GitHub. `.env` et `codelix.toml` restent locaux et ignorés par Git.
- **Skill Builder MVP :** gestion locale terminée et 93 tests passent. Création, validation, installation inactive, permissions, audit, configuration, mises à jour, désinstallation, contexte non fiable et contrôles statiques sont intégrés. L’exécution de code reste fermée : la sandbox avancée est post-MVP et aucun runtime isolé n’est disponible sur ce poste. Voir [`docs/skills/README.md`](docs/skills/README.md).

- **Cahier principal — contexte/reprise :** contexte compact conservé dans `.vybelix-cache/context.json`, validation par projet/taille/secret/chemins, édition dans Paramètres; reprise CLI/UI pour tâches bloquées ou interrompues, dépendances requises et confirmation, aucun agent lancé automatiquement.
- **Phase 2 :** terminée pour les fournisseurs conservés, après réussite des tests automatisés et confirmation de générations réelles. Groq reste exclu comme demandé.


## 2026-10-01 — Rôles d’agents, propositions JSON et diagnostics

- Le Planner est maintenant invité à livrer des tâches exécutables : Coder pour code/documentation, Tester pour tests; l’analyse n’est pas créée comme tâche différée. Les nouveaux plans sont rejetés si type et rôle sont incohérents.
- Prompts Coder et Tester séparés. Le Coder doit répondre en JSON brut strict, sans Markdown, avec les clés contractuelles et au moins une écriture lorsqu’une tâche l’exige. Verifier reste déterministe.
- La carte du plan permet de le désapprouver uniquement si ses tâches n’ont commencé et qu’aucune tâche externe n’en dépend.
- Notifications déplacées dans la barre d’état : messages conservés 60 secondes, cumulés et affichés sur plusieurs lignes.
- Statique : syntaxe Python/JavaScript et `git diff --check` valides. Les tests automatisés complets n’ont pas été relancés; aucun appel de génération n’a été effectué. Les routes Coder et le pipeline réel restent à confirmer.
