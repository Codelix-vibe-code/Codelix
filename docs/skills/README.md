# Skill Builder — MVP local contrôlé

Le MVP de gestion locale est implémenté : format, validation, installation désactivée, permissions explicites, configuration, diagnostics statiques, mise à jour et désinstallation. Aucun code fourni par un skill n’est exécuté.

## Commandes disponibles

- `vybelix skills create <id> --name ... --description ...` crée un brouillon sous `skills/<id>`.
- `vybelix skills validate <dossier>` valide un package local.
- `vybelix skills install <dossier>` affiche les permissions, demande confirmation, puis installe le package désactivé dans le cache local.
- `vybelix skills update <dossier>` installe une version strictement supérieure et la laisse désactivée afin de refaire la revue.
- `vybelix skills dependencies <id>` contrôle les dépendances déjà présentes, sans rien installer.
- `vybelix skills test <id>` lance les vérifications statiques du package et de son intégrité. Les tests arbitraires fournis par un skill ne sont pas exécutés.
- `vybelix skills configure <id> <config.json>` valide les valeurs contre `config_schema`. Les champs secrets sont séparés et chiffrés par DPAPI Windows lié à l’utilisateur; aucune valeur n’est renvoyée par l’interface. Un skill ne peut pas encore lire ces secrets pendant son exécution.
- `vybelix skills list`, `enable`, `disable` et `uninstall` gèrent le registre local. L’activation exige l’accord explicite sur chaque permission déclarée.

Les contrats sont décrits dans [`skill-v1.schema.json`](../../schemas/skill-v1.schema.json) et [`skill-capabilities-v1.schema.json`](../../schemas/skill-capabilities-v1.schema.json). Le cahier des charges complet fourni est archivé dans [`SPEC_SKILL_BUILDER.md`](SPEC_SKILL_BUILDER.md).

## Limites de cette tranche

- La vue Skills crée les brouillons, valide et met à jour les packages locaux, configure leurs paramètres, montre les diagnostics statiques et permet de prévisualiser les instructions pour Planner/Coder/Tester.
- Le `SkillBridge` ne fournit que les instructions des skills explicitement choisis, activés, intègres et dont les dépendances sont disponibles. Les contenus portent `UNTRUSTED_SKILL_DATA`; l’interface offre une prévisualisation locale.
- Aucun script/capability n’est exécuté : `execute()` refuse toute demande. Le poste contrôlé ne dispose pas d’un backend sandbox isolé validé; l’exécution reste fermée.
- Les tests de skill sont statiques. L’exécution du code et les tests qui le lanceraient restent désactivés; le cahier classe la sandbox avancée en post-MVP.
- Les sources distantes, marketplace, installations automatiques de dépendances et génération IA de skills ne sont pas intégrées.
- L’installation est locale seulement et nécessite une confirmation interactive.
- Le scanner de secrets et le contrôle d’intégrité ajoutent des garde-fous, sans remplacer une revue de sécurité dédiée.

## Limites de sécurité

- Aucune dépendance n’est téléchargée ni installée en arrière-plan; une dépendance absente/incompatible apparaît dans le diagnostic.
- Les nouvelles versions locales sont installées désactivées et les anciennes versions restent dans le cache pour permettre la revue/retour manuel.
- L’interface de prévisualisation locale du SkillBridge ne transmet pas le contenu aux modèles. L’ajout de ce contenu aux prompts distants nécessite l’accord explicite de l’utilisateur.
- Aucun runtime isolé n’est disponible sur le poste actuel (Windows Sandbox désactivé; Docker/Podman absents). WSL seul n’est pas traité comme une sandbox. Ne pas ouvrir l’exécution avant d’intégrer et de valider un backend avec fichiers isolés, réseau désactivé par défaut, délai maximal et sortie bornée.
