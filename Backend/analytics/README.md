# Analytics

API de statistiques descriptives en lecture seule pour les tableaux de bord Flutter.
Elle ne produit ni diagnostic, ni prédiction, ni recommandation et ne modifie aucune
mesure, alerte ou notification.

## Endpoints

- `GET /api/analytics/summary/` : dernières mesures, moyennes, volumes et alertes.
- `GET /api/analytics/blood-pressure/` : tension et fréquence cardiaque.
- `GET /api/analytics/blood-glucose/` : glycémie normalisée.
- `GET /api/analytics/hba1c/` : valeurs HbA1c et direction depuis le point précédent.
- `GET /api/analytics/alerts/` : distributions et évolution quotidienne, sans message.
- `GET /api/analytics/trends/` : comparaison neutre de deux fenêtres de sept jours.

Le patient est déduit du JWT et ne peut pas envoyer `patient_id`. Le médecin doit
envoyer `patient_id` et doit être actuellement affecté à ce patient actif. Les
administrateurs n'ont aucun accès médical implicite.

## Périodes, séries et unités

`period` accepte `7d`, `30d` (défaut), `90d`, `6m`, `1y` ou `custom`. Une période
custom exige `date_from` et `date_to`. Les bornes sont inclusives, interprétées et
retournées en UTC. La limite est configurable par `ANALYTICS_MAX_PERIOD_DAYS` et vaut
365 jours. Les intervalles sans données sont omis.

Les séries de tension et glycémie acceptent `raw`, `day`, `week` et `month`. Les
séries brutes sont paginées (50 par défaut, 100 maximum); les agrégats SQL bornés ne
le sont pas. Tension : mmHg; fréquence : bpm; HbA1c : `%`. La glycémie analytique
est toujours en `MG_PER_DL`, avec `1 g/L = 100 mg/dL`; les valeurs et unités originales
restent visibles dans les points bruts et la base n'est jamais modifiée.

Une tendance exige par défaut deux valeurs dans chacune des deux fenêtres. Elle
renvoie `UP`, `DOWN`, `STABLE` ou `INSUFFICIENT_DATA`, avec variation absolue et
pourcentage seulement lorsque le dénominateur est non nul. Ces directions ne portent
aucun jugement médical.

## Exploitation

Les agrégats utilisent `Avg`, `Min`, `Max`, `Count` et `TruncDay/Week/Month` après
filtrage SQL par patient et période. Chaque lecture produit un événement d'audit
minimal (endpoint, patient, période, granularité, statistique), jamais la série ni le
corps de réponse. Aucun cache n'est activé. Un futur cache partagé devra inclure
l'acteur, le patient, l'endpoint et tous les paramètres dans sa clé, avec une durée
courte et des tests d'isolation. Surveiller en production les séries brutes, les
regroupements longs et les répartitions de codes de règle.
