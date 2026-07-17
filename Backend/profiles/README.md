# Domaine profiles

`User` porte l'identité, le rôle et l'état du compte. `PatientProfile` et
`DoctorProfile` portent les informations propres à chaque métier. Un profil doit
toujours correspondre au rôle de son utilisateur.

## API mobile

- `GET /api/profiles/me/` : profil métier courant et état d'onboarding.
- `PATCH /api/profiles/me/` : modification des seuls champs autorisés.
- `GET /api/profiles/my-patients/` : patients actuellement affectés au médecin.
- `GET /api/profiles/my-doctors/` : médecins actuellement affectés au patient.
- `GET /api/profiles/assignments/` : historique personnel paginé.

Il n'existe ni endpoint générique par UUID, ni annuaire global. Les listes sont
paginées à 20 éléments par défaut et 100 maximum. Elles acceptent des bornes sur
`assigned_at` et un tri chronologique; l'historique accepte aussi `status`.

## Exposition et modification

Le profil propre expose l'identité minimale du compte et les champs métier. Le
patient peut modifier `date_naissance`, `sexe`, `poids` et `taille`. Le médecin
peut modifier `specialite`, `hopital` et `annees_experience`. Le propriétaire,
le rôle, les UUID, les dates système et `numero_ordre` sont immuables dans l'API.
Les noms et le téléphone restent gérés par `/api/auth/me/`.

`antecedents` n'est jamais exposé ici : les informations médicales détaillées
restent dans leurs domaines dédiés. Les listes de patients ne contiennent pas
d'e-mail, mesure, traitement, document ou dossier médical. Les listes de médecins
n'exposent que le nom d'affichage, la spécialité et l'établissement, sans numéro
d'ordre ni information administrative.

## Onboarding

`get_profile_completion()` calcule à la volée `is_complete`,
`completion_percentage` et `missing_fields`. Aucun pourcentage n'est stocké. Les
champs requis dépendent du rôle et incluent les coordonnées de compte nécessaires
ainsi que les champs métier existants. Les champs administratifs ne bloquent pas
l'onboarding.

L'inscription publique crée atomiquement le compte `PATIENT` et son
`PatientProfile`. Les données d'onboarding qui ne sont pas demandées à
l'inscription (`date_naissance`, `sexe`, `poids`, `taille`) restent à `NULL` :
aucune valeur médicale fictive n'est inventée. La réponse v1 contient l'UUID du
profil et sa complétude. Après connexion, `GET /api/v1/profiles/me/` retourne donc
immédiatement 200 et `PATCH /api/v1/profiles/me/` permet de terminer l'onboarding.

Les comptes patients historiques sans profil peuvent être inspectés puis réparés
sans toucher aux médecins ou administrateurs :

```bash
python manage.py repair_missing_profiles --dry-run
python manage.py repair_missing_profiles
```

La commande est idempotente et n'affiche ni e-mail, ni mot de passe, ni donnée
médicale.

## Affectations

`PatientDoctorAssignment` conserve l'historique. Une affectation est active lorsque
son statut vaut `ACTIVE`, que sa date de fin est vide et que les deux comptes sont
actifs. Une ligne terminée reste visible dans l'historique mais ne donne aucun accès
médical. `doctor_can_access_patient()` reste l'autorité pour cet accès.

L'API mobile ne permet ni création, ni modification, ni fin d'affectation. Ces
opérations restent dans l'administration Django et les services transactionnels
`assign_doctor_to_patient()` et `end_doctor_patient_assignment()`. Un futur flux
d'invitation et d'acceptation pourra être ajouté sans transformer les listes en
annuaire ni exposer directement ces services à tout médecin.

Les lectures et modifications sont auditées avec l'opération et les noms de champs
modifiés uniquement. Aucun profil complet ni valeur sensible n'est copié dans le
journal.
