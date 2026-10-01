# Reprise locale Vybelix

Mise à jour : 2026-10-01 (UTC).

## État de la demande actuelle

- Le sélecteur Modèles persiste les candidats ordonnés dans `[models]` du TOML actif; il sait configurer Planner, Coder et Tester, choisir principal/secours et retirer une route.
- Paramètres → API Keys enregistre localement les clés via le backend et peut affecter le modèle sélectionné à un agent. Les valeurs ne sont jamais renvoyées au navigateur après soumission. Le fichier `.env` reste en clair sur disque.
- La wheel a été construite puis installée dans un venv temporaire Python 3.12.10. Les imports `vybelix`/`codelix`, la ressource UI empaquetée, les deux commandes CLI et la suite de 77 tests passent.
- Le contexte compact projet est accessible par `vybelix context show/update` et Paramètres dans le cockpit; stockage local validé, sans envoi automatique aux modèles.
- La reprise CLI/UI remet uniquement les tâches `blocked`/`interrupted` en `todo` après confirmation et dépendances terminées; aucun agent n’est lancé automatiquement.
- Phase 2 demeure `needs_review`; ce chantier n’a modifié aucun adaptateur ou routage et n’a lancé aucun appel fournisseur.
- Les fichiers de progression, statut et sessions ont été remis à jour.

## Dépôt et précautions

- Projet : `C:\Users\Koko\Desktop\Project_Vybelix`.
- Branche `main`, dernier commit distant confirmé : `daafe99`.
- Le worktree contient des changements locaux/non publiés de plusieurs chantiers. Le Skill Builder et ses fichiers ne doivent pas être mélangés aux commits API/UI sans demande ciblée. Ne pas nettoyer ni réinitialiser.
- Le cahier source est conservé localement; sa copie suivie complète est `docs/progress/PROJECT_BRIEF.md`.

## Suite recommandée

1. Faire une revue visuelle navigateur des formulaires API Keys et Modèles après rafraîchissement dur.
2. Si l’utilisateur le demande, tester explicitement les appels fournisseurs autorisés; distinguer erreurs de clé, modèle, quota et service. Ne pas lancer d’appel de génération automatiquement.
3. Garder la phase 2 en revue tant que Planner, Coder et Tester n’ont pas les accès requis confirmés.
4. Le MVP local Skill Builder est terminé. Garder l’exécution de code désactivée; l’ouverture nécessitera un backend OS isolé validé (sandbox avancée post-MVP). La suite complète contient maintenant 93 tests.
5. Ne publier que des chemins ciblés après vérification de `git status`; le worktree contient des changements d’autres sujets.
