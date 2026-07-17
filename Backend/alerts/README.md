# Moteur d'alertes médicales

Le moteur détecte des mesures nécessitant une attention selon des seuils déterministes. Il ne pose aucun diagnostic, ne prescrit rien et ne modifie jamais un traitement. Les seuils fournis dans les settings sont destinés au développement et aux tests : ils doivent être validés par un professionnel de santé avant tout déploiement réel.

Règles disponibles : `BP_VERY_LOW`, `BP_ELEVATED`, `BP_VERY_HIGH`, `BP_CRITICAL_COMBINATION`, `HR_LOW`, `HR_HIGH`, `GLUCOSE_VERY_LOW`, `GLUCOSE_HIGH`, `GLUCOSE_VERY_HIGH` et `HBA1C_HIGH`. La conversion d'évaluation est centralisée : `1 g/L = 100 mg/dL`; la valeur enregistrée n'est jamais modifiée.

Une mesure et un code de règle ne peuvent produire qu'une alerte. Une nouvelle mesure similaire produit une nouvelle alerte. Lors d'un PATCH médical, la même mesure est réévaluée; une mesure corrigée ne supprime et ne résout jamais automatiquement l'alerte historique, mais ajoute `measurement_corrected` à ses métadonnées.

Transitions : `OPEN → ACKNOWLEDGED → RESOLVED`, ou `OPEN/ACKNOWLEDGED → DISMISSED` avec motif. Elles sont réservées au médecin actuellement affecté. Les patients disposent uniquement de LIST/GET sur leurs propres alertes. Les administrateurs n'obtiennent aucun accès implicite via l'API. `PUT`, `DELETE` et PATCH générique sont désactivés.

Les créations et transitions sont inscrites dans `medical_audit`. Aucune notification, analyse prédictive ou IA n'est implémentée; les codes stables sont prêts pour de futures notifications explicites et contrôlées.
