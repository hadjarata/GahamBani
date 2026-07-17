# Enums publics API v1

OpenAPI reste la source machine-lisible. Cette synthèse facilite le mapping Flutter.

- Rôle : `PATIENT`, `DOCTOR`, `ADMIN`.
- Sexe : `MALE`, `FEMALE`, `OTHER`.
- Affectation : `ACTIVE`, `ENDED`.
- Unité glycémie : `G_PER_L`, `MG_PER_DL`.
- Type glycémie : `FASTING`, `POST_MEAL`, `RANDOM`.
- Contexte repas : `BEFORE_MEAL`, `AFTER_MEAL`, `NO_MEAL`.
- Source mesure : `MANUAL`, `DEVICE`, `CONNECTED_DEVICE`.
- Contexte tension : `REST`, `EXERCISE`, `STRESS`, `ILLNESS`.
- Position : `SITTING`, `STANDING`, `LYING`.
- Bras : `LEFT`, `RIGHT`, `BOTH`.
- Prélèvement : `CAPILLARY`, `LABORATORY`, `SENSOR`.
- Type alerte : `HYPERTENSION`, `DIABETES`, `HEART_RATE`, `GENERAL`.
- Gravité alerte : `INFO`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.
- Statut alerte : `OPEN`, `ACKNOWLEDGED`, `RESOLVED`, `DISMISSED`.
- Source alerte : `SYSTEM_RULE`, `DOCTOR`, `MANUAL`.
- Notification : `MEDICAL_ALERT_CREATED`, `ALERT_ACKNOWLEDGED`,
  `ALERT_RESOLVED`, `ALERT_DISMISSED`, `SYSTEM`.
- Priorité notification : `LOW`, `NORMAL`, `HIGH`, `CRITICAL`.
- Granularité analytics : `raw`, `day`, `week`, `month`.
- Période analytics : `7d`, `30d`, `90d`, `6m`, `1y`, `custom`.
- Groupe sanguin : `A_POSITIVE`, `A_NEGATIVE`, `B_POSITIVE`, `B_NEGATIVE`,
  `AB_POSITIVE`, `AB_NEGATIVE`, `O_POSITIVE`, `O_NEGATIVE`, `UNKNOWN`.
- Gravité dossier : `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` selon la ressource.
- Statut maladie : `ACTIVE`, `INACTIVE`, `CONTROLLED`.
- Statut traitement : `ACTIVE`, `STOPPED`, `COMPLETED`.
- Type document : `ORDONNANCE`, `ANALYSE`, `RADIO`, `COMPTE_RENDU`,
  `CERTIFICAT`, `AUTRE`.
- Source upload : `PATIENT`, `DOCTOR`, `LEGACY`.

Les valeurs sont sensibles à la casse. Flutter doit conserver une branche `unknown`
locale afin de rester robuste face à une future valeur ajoutée compatible.
