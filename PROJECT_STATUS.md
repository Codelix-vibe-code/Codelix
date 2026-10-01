# État du projet Vybelix

- **Dépôt :** [Vybelix/Vybelix](https://github.com/Vybelix/Vybelix), branche `main`; dernier commit distant confirmé avant ces changements : `daafe99`.
- **Progression de référence :** [`docs/progress/tasks.json`](docs/progress/tasks.json), mise à jour le 1er octobre 2026.
- **Cahier des charges :** copie complète suivie dans [`docs/progress/PROJECT_BRIEF.md`](docs/progress/PROJECT_BRIEF.md); la copie source locale ignorée par Git reste conservée.
- **Phases MVP :** phases 0, 1, 3, 4 et 5 terminées; le contexte compact local (CLI + Paramètres du cockpit) et la reprise confirmée des tâches sont ajoutés; Phase 2 en `needs_review` : 92 tests passent après ajout des fonctions de contexte et de reprise; une erreur 401 passe désormais au candidat de secours. NVIDIA GPT-OSS répond au prompt minimal, mais l’essai Planner a expiré sur GPT-OSS et GLM à 60 s; Gemini 401, Groq 403, OpenRouter network error without HTTP status, Mistral 429.
- **Fournisseurs :** Gemini, OpenAI, Anthropic/Claude, NVIDIA, Groq, OpenRouter et Mistral sont raccordés au routeur local. NVIDIA GPT-OSS répond au prompt minimal; le smoke Planner a atteint le fallback mais n’a pas fourni de plan valide. Coder, application et vérification complets restent à confirmer. Les routes Planner/Coder/Tester sont maintenant modifiables depuis Modèles ou lors de l’ajout d’une clé API.
- **Installation :** wheel construite et installée sous Python 3.12.10 dans un venv temporaire; ressources UI, imports `vybelix`/`codelix`, commandes CLI et 78 tests vérifiés.
- **API Keys :** gestionnaire relié au `.env` local ignoré par Git. Les clés ne sont pas chiffrées sur disque; le PIN protège l’accès à l’interface uniquement.
- **Changements locaux :** plusieurs fichiers demeurent modifiés/non suivis, dont le Skill Builder d’un autre chantier. Préserver leur contenu et ne pas les inclure dans une publication non ciblée.
- **Skill Builder MVP :** gestion locale terminée et 93 tests passent. Création, validation, installation inactive, permissions, audit, configuration, mises à jour, désinstallation, contexte non fiable et contrôles statiques sont intégrés. L’exécution de code reste fermée : la sandbox avancée est post-MVP et aucun runtime isolé n’est disponible sur ce poste. Voir [`docs/skills/README.md`](docs/skills/README.md).

- **Cahier principal — contexte/reprise :** contexte compact conservé dans `.vybelix-cache/context.json`, validation par projet/taille/secret/chemins, édition dans Paramètres; reprise CLI/UI pour tâches bloquées ou interrompues, dépendances requises et confirmation, aucun agent lancé automatiquement.
- **Phase 2 :** conservée ouverte (`needs_review`); aucun adaptateur, routage ni appel réel modifié ou exécuté pendant ce travail.


## 2026-10-01 — Rôles d’agents, propositions JSON et diagnostics

- Le Planner est maintenant invité à livrer des tâches exécutables : Coder pour code/documentation, Tester pour tests; l’analyse n’est pas créée comme tâche différée. Les nouveaux plans sont rejetés si type et rôle sont incohérents.
- Prompts Coder et Tester séparés. Le Coder doit répondre en JSON brut strict, sans Markdown, avec les clés contractuelles et au moins une écriture lorsqu’une tâche l’exige. Verifier reste déterministe.
- La carte du plan permet de le désapprouver uniquement si ses tâches n’ont commencé et qu’aucune tâche externe n’en dépend.
- Notifications déplacées dans la barre d’état : messages conservés 60 secondes, cumulés et affichés sur plusieurs lignes.
- Statique : syntaxe Python/JavaScript et `git diff --check` valides. Les tests automatisés complets n’ont pas été relancés; aucun appel de génération n’a été effectué. Les routes Coder et le pipeline réel restent à confirmer.
