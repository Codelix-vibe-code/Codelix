# Migration Codelix vers Vybelix

Le package principal, le nom de distribution, la commande recommandée, la configuration neuve, les chemins de cache et le branding visible utilisent désormais Vybelix.

## Compatibilité conservée

- `codelix` reste un alias de commande et un namespace Python de transition. Les noms `CodelixConfig` et `CodelixWorkflow` restent des alias des classes Vybelix.
- `codelix.toml` est chargé uniquement si `vybelix.toml` n’existe pas. Les initialisations neuves utilisent `vybelix.toml`; aucun fichier existant n’est déplacé ou écrasé.
- `.codelix-cache` et `.codelix-backups` ne sont jamais supprimés. Quand le nouveau répertoire correspondant n’existe pas, l’ancien emplacement reste utilisé pour préserver les données locales. En cas de coexistence, le nouvel emplacement prévaut.
- Les clés `localStorage` et identifiants SVG historiques sont conservés pour préserver les préférences existantes. Les URI `$id` `codelix.dev` des schémas restent stables afin de ne pas invalider les consommateurs qui les référencent.
- Les historiques `docs/progress/tasks.json`, `PROJECT_STATUS.md`, `sessions.md` et le cahier des charges gardent leur contexte historique.

Le dépôt Git distant actuel n’a pas été renommé ni modifié. Son changement vers `Vybelix/Vybelix` doit être réalisé côté GitHub, puis le remote `origin` pourra être actualisé. Le Skill Builder n’est pas présent dans le dépôt actuel; cette migration ne l’ajoute ni ne le modifie.
