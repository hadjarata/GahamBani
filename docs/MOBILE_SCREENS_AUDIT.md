# Audit backend — écrans et fonctionnalités de l’application mobile

Date de l’audit : 27 juillet 2026  
Périmètre : API Django REST v1 et squelette Expo présents dans le dépôt.

## 1. Résumé

Le backend expose 64 opérations sous `/api/v1/` et permet de construire deux
parcours mobiles :

- **Patient** : inscription, onboarding, saisie des mesures, suivi, alertes,
  notifications et consultation du dossier médical.
- **Médecin** : sélection d’un patient affecté, consultation de son suivi,
  traitement des alertes et gestion de son dossier médical.

Le projet mobile est encore un squelette Expo : aucun parcours métier n’y est
implémenté. L’application doit donc être construite à partir du contrat API v1.

### Navigation recommandée

**Patient**

`Accueil` · `Mesures` · `Suivi` · `Dossier` · `Profil`

Les alertes et notifications sont accessibles depuis l’Accueil et une cloche
globale.

**Médecin**

`Patients` · `Alertes` · `Notifications` · `Profil`

Après sélection d’un patient, une fiche patient donne accès à `Synthèse`,
`Mesures`, `Dossier` et `Alertes`.

## 2. Écrans communs

| ID | Écran | Priorité | Fonctionnalités | API |
|---|---|---:|---|---|
| C01 | Splash / démarrage | MVP | Restaurer la session sécurisée, rafraîchir le jeton une seule fois si nécessaire, charger le profil, rediriger selon le rôle et l’onboarding | `POST auth/refresh`, `GET profiles/me` |
| C02 | Connexion | MVP | Email, mot de passe, affichage des erreurs, lien mot de passe oublié ; stockage sécurisé des jetons | `POST auth/login` |
| C03 | Inscription patient | MVP | Prénom, nom, email, téléphone, mot de passe et confirmation ; connexion demandée après succès | `POST auth/register` |
| C04 | Mot de passe oublié | MVP | Envoyer l’email sans révéler si le compte existe ; afficher un message neutre | `POST auth/password-reset` |
| C05 | Nouveau mot de passe | MVP | Ouvrir le lien profond reçu, transmettre `uid` et `token`, saisir et confirmer le nouveau mot de passe | `POST auth/password-reset-confirm` |
| C06 | Notifications | MVP | Liste paginée, filtres lu/non lu, priorité et type, badge non-lus, pull-to-refresh, « tout marquer comme lu » | `GET notifications`, `GET notifications/unread-count`, `PATCH notifications/{id}/read`, `PATCH notifications/read-all` |
| C07 | Détail notification | MVP | Titre, message, priorité, date, état lu ; marquer comme lue ; ouvrir la ressource liée si `source_*` et `metadata` sont reconnus | `GET notifications/{id}`, `PATCH notifications/{id}/read` |
| C08 | Mon compte | MVP | Afficher email, rôle, vérification ; modifier prénom, nom et téléphone | `GET/PATCH auth/me` |
| C09 | Mon profil métier | MVP | Afficher et modifier les champs autorisés selon le rôle ; montrer le taux de complétion | `GET/PATCH profiles/me` |
| C10 | Sécurité | MVP | Changer le mot de passe actuel ; déconnecter la session courante | `POST auth/change-password`, `POST auth/logout` |
| C11 | Historique des affectations | P2 | Liste active/terminée, dates et contrepartie, filtres par statut/date | `GET profiles/assignments` |

### Règles communes à prévoir

- États `chargement`, `vide`, `hors-ligne`, `403`, `404`, `429` et erreur
  inconnue sur chaque écran réseau.
- Pagination et pull-to-refresh sur toutes les listes.
- Jetons uniquement dans le stockage sécurisé natif, jamais dans les logs.
- Un seul refresh simultané ; déconnexion forcée si le refresh échoue.
- Dates affichées dans le fuseau de l’utilisateur, données envoyées en ISO 8601.
- Valeurs décimales reçues comme chaînes puis formatées côté présentation.
- Écran/boîte de dialogue de confirmation avant une modification médicale.

## 3. Parcours patient

| ID | Écran | Priorité | Fonctionnalités | API |
|---|---|---:|---|---|
| P01 | Onboarding santé | MVP | Compléter uniquement les champs retournés dans `missing_fields` : date de naissance, sexe, poids, taille ; progression et validation | `GET/PATCH profiles/me` |
| P02 | Accueil patient | MVP | Dernières tension, glycémie et HbA1c, compteurs de mesures, alertes ouvertes, date du dernier relevé, raccourcis « ajouter une mesure » | `GET analytics/summary`, `GET notifications/unread-count` |
| P03 | Choisir une mesure | MVP | Deux actions : tension artérielle ou glycémie | Navigation locale |
| P04 | Ajouter une tension | MVP | Systolique, diastolique, fréquence cardiaque optionnelle, contexte, position, bras, numéro de mesure, notes et date/heure | `POST monitoring/blood-pressure` |
| P05 | Ajouter une glycémie | MVP | Valeur, unité, type de mesure, HbA1c optionnelle, contexte repas, heure, prélèvement, notes et date/heure | `POST monitoring/blood-glucose` |
| P06 | Historique des mesures | MVP | Onglets tension/glycémie, pagination, filtre date, tri, résumé de la valeur et du contexte | `GET monitoring/blood-pressure`, `GET monitoring/blood-glucose` |
| P07 | Détail / corriger une mesure | MVP | Voir tous les champs ; modifier sa propre mesure ; aucune suppression car l’API ne l’expose pas | `GET/PATCH monitoring/{type}/{id}` |
| P08 | Suivi et graphiques | MVP | Sélecteur 7 j, 30 j, 90 j, 6 mois, 1 an ou dates personnalisées ; courbes tension, glycémie et HbA1c ; granularité jour/semaine/mois ; indicateurs de tendance | `GET analytics/blood-pressure`, `blood-glucose`, `hba1c`, `trends` |
| P09 | Mes alertes | MVP | Liste filtrable par sévérité, statut, type/règle et dates ; code couleur accessible ; patient en lecture seule | `GET alerts` |
| P10 | Détail alerte | MVP | Message, gravité, statut, valeur observée, unité, date, historique des transitions ; aucune action de transition pour le patient | `GET alerts/{id}` |
| P11 | Mon dossier médical | MVP | Résumé du dossier et accès aux sections maladies, allergies, traitements, consultations, notes et documents | `GET medical-records/record` + listes associées |
| P12 | Liste clinique | MVP | Un composant décliné en cinq sections : maladies, allergies, traitements, consultations, notes ; filtres date/statut et détail | `GET medical-records/{section}` |
| P13 | Documents médicaux | MVP | Liste, filtre type/date, détail, téléchargement authentifié et ouverture locale sécurisée | `GET medical-records/documents`, `GET documents/{id}/download` |
| P14 | Ajouter un document | MVP | Choisir appareil photo ou fichier, titre, type, description, date ; progression d’upload ; validation taille/MIME | `POST medical-records/documents` en multipart |
| P15 | Mes médecins | P2 | Médecins actuellement affectés, spécialité, hôpital et date d’affectation | `GET profiles/my-doctors` |

## 4. Parcours médecin

| ID | Écran | Priorité | Fonctionnalités | API |
|---|---|---:|---|---|
| D01 | Mes patients | MVP | Liste paginée des patients actuellement affectés, recherche locale sur les pages chargées, tri par date ; sélection obligatoire depuis cette liste | `GET profiles/my-patients` |
| D02 | Fiche patient — synthèse | MVP | Identité disponible, dernières mesures, moyennes, compteurs, alertes et tendances ; sélecteur de période | `GET analytics/summary`, `GET analytics/trends` avec `patient_id` |
| D03 | Fiche patient — mesures | MVP | Historique et graphiques tension/glycémie/HbA1c ; filtres et pagination ; lecture seule | `GET monitoring/*`, `GET analytics/*` avec `patient_id` |
| D04 | Alertes patient | MVP | Alertes filtrées du patient, compteur par statut/sévérité, accès au détail | `GET alerts`, `GET analytics/alerts` avec `patient_id` |
| D05 | Traiter une alerte | MVP | Acquitter, résoudre ou rejeter selon l’état courant ; motif optionnel ; retour immédiat de l’alerte mise à jour | `PATCH alerts/{id}/acknowledge`, `resolve`, `dismiss` |
| D06 | Dossier du patient | MVP | Résumé et sections maladies, allergies, traitements, consultations, notes et documents | `GET medical-records/*` avec `patient_id` |
| D07 | Ajouter / modifier une maladie | MVP | Nom, diagnostic, résolution, gravité, statut, notes | `POST/PATCH medical-records/chronic-diseases` |
| D08 | Ajouter / modifier une allergie | MVP | Nom, gravité, réaction, active/inactive, notes | `POST/PATCH medical-records/allergies` |
| D09 | Ajouter / modifier un traitement | MVP | Médicament, description, dosage, fréquence, voie, dates, statut et notes | `POST/PATCH medical-records/treatments` |
| D10 | Ajouter / modifier une consultation | MVP | Date, motif, diagnostic, symptômes, observations et notes | `POST/PATCH medical-records/consultations` |
| D11 | Ajouter / modifier une note | MVP | Contenu de la note ; auteur automatiquement fixé par le backend | `POST/PATCH medical-records/notes` |
| D12 | Documents du patient | MVP | Liste, détail, téléchargement et téléversement pour le patient sélectionné | `GET/POST medical-records/documents`, `GET download` |

### Sécurité du contexte patient

Le `patient_id` utilisé par un médecin doit toujours provenir de
`profiles/my-patients`. Il doit être conservé dans un contexte de navigation
explicite, vidé à la déconnexion et ne jamais être saisi manuellement. Une
affectation `ENDED` reste visible dans l’historique mais interdit tout accès
médical.

## 5. Matrice des droits à refléter dans l’interface

| Domaine | Patient | Médecin affecté |
|---|---|---|
| Mesures tension/glycémie | Lire, créer, corriger les siennes | Lecture seule |
| Analytics | Ses propres données | Données du patient sélectionné |
| Alertes | Lecture seule | Lire et changer le statut |
| Maladies/allergies/traitements/consultations/notes | Lecture seule | Créer et modifier |
| Documents | Lire, téléverser, télécharger | Lire, téléverser, télécharger |
| Profil | Modifier ses champs autorisés | Modifier ses champs autorisés |
| Affectations | Consulter | Consulter |

## 6. Fonctionnalités non supportées par le backend

Ces éléments ne doivent pas apparaître comme fonctionnels dans le MVP sans
extension préalable de l’API :

- vérification d’adresse email ;
- inscription autonome d’un médecin ;
- création, modification ou fin d’une affectation patient–médecin ;
- rendez-vous et calendrier ;
- messagerie patient–médecin, appel audio ou vidéo ;
- enregistrement d’un appareil et envoi de push natif ;
- suppression de mesures ou d’éléments du dossier ;
- modification du groupe sanguin et du résumé historique du dossier ;
- création manuelle d’une alerte ;
- synchronisation réelle avec un tensiomètre ou glucomètre connecté.

Le champ `source_mesure` est en lecture seule et sera actuellement `MANUAL`.

## 7. Points backend à clarifier avant finition UX

1. **Création des médecins et affectations** : le mobile peut les afficher mais
   aucune route v1 ne permet de les administrer.
2. **Email de réinitialisation** : valider le schéma de lien profond mobile et
   les domaines universels/app links.
3. **Push** : les notifications existent en base, mais aucun endpoint
   d’enregistrement de token push n’est exposé.
4. **Documents** : exposer clairement dans le contrat la taille maximale et les
   MIME types autorisés afin de valider avant l’upload.
5. **Transitions d’alerte** : documenter la matrice exacte des transitions pour
   activer/désactiver les boutons sans attendre un rejet serveur.
6. **Recherche patient** : l’API offre pagination et tri mais pas de paramètre de
   recherche ; une recherche globale nécessite une évolution backend.

## 8. Découpage conseillé

### Lot 1 — socle

C01 à C10, gestion des erreurs, client API, stockage sécurisé et navigation par
rôle.

### Lot 2 — patient MVP

P01 à P14 : accueil, saisie, historique, graphiques, alertes et dossier.

### Lot 3 — médecin MVP

D01 à D12 : sélection sécurisée du patient, suivi, alertes et gestion clinique.

### Lot 4 — amélioration

C11, P15, cache hors-ligne en lecture, accessibilité renforcée et évolutions
backend listées plus haut.

## 9. Sources auditées

- `Backend/openapi-v1.yaml`
- `Backend/docs/api-v1.md`
- `Backend/docs/api-v1-routes.md`
- `Backend/docs/api-v1-enums.md`
- vues, permissions, serializers, modèles et services des domaines `accounts`,
  `profiles`, `monitoring`, `analytics`, `alerts`, `notifications` et
  `medical_records`
- squelette `mobile/gahambani-mobile`
