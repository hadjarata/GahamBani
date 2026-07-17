# Contrat mobile GahamBani API v1

Version API : `v1`. Version applicative initiale : `0.1.0`.

La base officielle est `/api/v1/`. En développement local :

- Android Emulator : `http://10.0.2.2:8000/api/v1/`
- iOS Simulator : `http://127.0.0.1:8000/api/v1/`
- appareil physique : `http://<IP_LOCALE>:8000/api/v1/`

L’adresse physique doit être explicitement ajoutée à `DJANGO_ALLOWED_HOSTS` et
l’origine Flutter web à `DJANGO_CORS_ALLOWED_ORIGINS`. HTTP est réservé au
développement local. Staging et production exigent HTTPS et n’acceptent aucun host
générique.

## Versionnement et compatibilité

Les anciennes routes `/api/<domaine>/` restent temporairement disponibles comme
aliases dépréciés utilisant exactement les mêmes vues. Elles ne recevront aucune
nouvelle fonctionnalité et seront supprimées après une fenêtre de migration mobile
annoncée. Toute rupture de champ, d’enum, de méthode ou de sémantique exigera `/api/v2/`
ou une dépréciation documentée.

Le contrat source est [openapi-v1.yaml](../openapi-v1.yaml), consultable sur
`/api/schema/v1/`, `/api/docs/v1/` et `/api/redoc/v1/`. L’inventaire lisible se trouve
dans [api-v1-routes.md](api-v1-routes.md).

Régénération reproductible :

```bash
python manage.py spectacular --validate --file openapi-v1.yaml --settings=config.settings.test
python scripts/generate_api_inventory.py openapi-v1.yaml docs/api-v1-routes.md
```

## Authentification

Les routes protégées utilisent `Authorization: Bearer <access_token>`. Après login,
les jetons doivent être conservés dans le stockage sécurisé fourni par la plateforme
mobile, jamais dans des préférences ou logs en clair.

L’access token expire rapidement. Flutter tente un refresh une seule fois après un
401 `invalid_token`, remplace atomiquement les deux jetons en cas de succès, puis
rejoue la requête. Si le refresh échoue, il supprime les jetons et force la connexion.
Un changement ou une réinitialisation du mot de passe invalide les anciens jetons.

### Inscription patient et onboarding

`POST /api/v1/auth/register/` accepte uniquement `first_name`, `last_name`,
`email`, `phone`, `password` et `password_confirm`. Le backend impose le rôle
`PATIENT`; les champs de privilège ou d'état (`role`, `is_staff`,
`is_superuser`, `is_verified`, `is_active`, groupes, permissions et version de
jeton) sont refusés.

Le compte et son `PatientProfile` sont créés dans la même transaction. La date de
naissance, le sexe, le poids et la taille ne sont pas demandés à cette étape et
restent nuls, sans valeur fictive. La réponse 201 retourne l'identité minimale,
l'UUID du profil et :

```json
{
  "onboarding": {
    "is_complete": false,
    "completion_percentage": 43,
    "missing_fields": ["date_naissance", "sexe", "poids", "taille"]
  }
}
```

Aucun access token ou refresh token n'est émis à l'inscription. Le client se
connecte ensuite par `auth/login`, consulte `profiles/me`, puis complète les
champs manquants par `PATCH /api/v1/profiles/me/`. Une adresse déjà utilisée
retourne 409 `conflict`.

Le compte est créé avec `is_verified=false`. À ce stade du projet, aucun parcours
de vérification d'adresse e-mail n'est encore implémenté et l'inscription ne
simule aucune vérification; l'état est seulement conservé pour ce futur flux.

## Réponses

Un détail retourne directement la ressource. Les collections utilisent :

```json
{"count": 1, "next": null, "previous": null, "results": []}
```

Les compteurs conservent un nom explicite, par exemple `unread_count`. Les actions
retournent la ressource mise à jour lorsqu’elle est utile, sinon un objet contenant
un message. Toutes les dates sont ISO 8601 avec timezone et l’API fonctionne en UTC.
Les UUID sont des chaînes. Les décimales médicales peuvent être des chaînes JSON :
Flutter ne doit pas les convertir avec une locale utilisateur.

## Erreurs v1

```json
{
  "code": "validation_error",
  "detail": "Les données fournies sont invalides.",
  "errors": {"field": ["Message précis."]}
}
```

Codes généraux :

- `authentication_required` : jeton absent sur une route protégée.
- `invalid_token` : jeton invalide, expiré ou révoqué.
- `permission_denied` : utilisateur authentifié sans permission.
- `not_found` : ressource absente ou volontairement masquée.
- `validation_error` : paramètres ou champs invalides; consulter `errors`.
- `method_not_allowed` : méthode HTTP non exposée.
- `throttled` : limite atteinte; `retry_after` peut être présent.
- `conflict` : état concurrent incompatible avec la demande.
- `business_rule_violation` : règle métier empêchant l’opération.
- `profile_missing` : compte actif sans profil correspondant à son rôle.
- `profile_creation_failed` : création du profil impossible; la création du compte
  a été annulée par la transaction.

Codes métier réservés au contrat et à introduire seulement sur les opérations
concernées : `inactive_account`, `invalid_assignment`, `doctor_not_assigned`,
`invalid_alert_transition`, `invalid_date_range`, `period_too_long`,
`unsupported_file_type`, `file_too_large`. Flutter doit toujours prévoir un repli
sur `code` inconnu et ne doit pas analyser les phrases de `detail`.

## Pagination, filtres et throttling

La plupart des listes acceptent `page` et `page_size`, avec un maximum de 100.
Analytics ajoute `unit` et `granularity` autour de la même structure. Les filtres
acceptés sont décrits opération par opération dans OpenAPI. Un 429 utilise le code
`throttled`; Flutter respecte `retry_after` et évite les boucles automatiques.

## Fichiers

L’upload de documents utilise `multipart/form-data` sur la route documentée. Flutter
ne doit ni inventer le MIME type ni envoyer un fichier dépassant la limite annoncée.
Le téléchargement utilise la route authentifiée `documents/{id}/download/`, traite
une réponse binaire et ne journalise jamais l’URL comme publique.

## Parcours Flutter

Connexion : `auth/login` → stockage sécurisé → `profiles/me` → navigation par rôle
et onboarding. Le compte incomplet utilise `missing_fields`; aucun rôle n’est déduit
du contenu d’un écran.

Patient : profil → tension/glycémie → historique monitoring → analytics → alertes →
notifications → dossier médical. Le patient n’envoie jamais un autre `patient_id`.

Médecin : profil → `profiles/my-patients` → choix d’un patient actif → analytics →
mesures → dossier → alertes. Le choix patient doit provenir de cette liste, jamais
d’un UUID saisi librement.

Refresh : renouveler juste avant expiration ou après le premier 401; ne jamais lancer
plusieurs refresh concurrents; déconnecter si le refresh est rejeté.

## Sécurité mobile

- Ne jamais afficher ni journaliser access/refresh token.
- Ne jamais conserver une URL de téléchargement comme URL publique permanente.
- Ne pas interpréter une affectation terminée comme un accès médical.
- Ne pas faire confiance aux contrôles d’écran : le backend reste l’autorité.
- Ne jamais transmettre de données médicales à des services de télémétrie tiers.

## Démonstration locale

```bash
python manage.py seed_demo_data --settings=config.settings.development
python manage.py seed_demo_data --password "UnSecretLocalFort" --settings=config.settings.development
```

La commande est idempotente, exclusivement locale, et utilise uniquement des noms,
emails `.invalid`, numéros et données marqués `DEMO`. Elle est refusée lorsque
`ALLOW_DEMO_DATA` n’est pas explicitement activé.
