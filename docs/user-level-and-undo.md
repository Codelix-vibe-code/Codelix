# Niveau utilisateur et annulation

Vybelix propose trois niveaux de communication. Ils ne changent jamais les validations, les approbations, les contrôles de chemins, ni les règles du Verifier.

    vybelix level beginner
    vybelix level intermediate
    vybelix level pro

Si la configuration ne contient pas encore la table [user], le niveau beginner est utilisé par défaut. La commande met à jour user.level dans le fichier TOML du projet.

- beginner : résumé de plan en langage simple, rapports expliqués et explication automatique après application.
- intermediate : plan standard et résultats structurés. L’option --explain de la commande apply affiche l’explication à la demande.
- pro : affichage concis et technique, explication désactivée par défaut. L’option --explain permet de la demander explicitement.

Les contrats Planner et Coder acceptent les versions 1.0 et 1.1. plain_summary et explanation sont optionnels : leur absence ne rejette pas une réponse antérieure. L’explication du Coder est informative ; seul le résultat réel du Verifier peut établir qu’une tâche est vérifiée.

## Annuler le dernier changement

    vybelix undo

La commande montre les fichiers ciblés puis demande une confirmation. Elle refuse l’annulation si un fichier a changé depuis l’application, et ne l’écrase pas. Les points de retour créés avant l’ajout des manifestes d’annulation ne peuvent pas être annulés par cette commande.

Le suivi anticipé des quotas et la commande quotas restent en attente de la phase 2.
