# API des dossiers médicaux

Toutes les routes sont sous `/api/medical-records/` et exigent un JWT. Un patient lit son propre dossier et ses données cliniques, et peut uniquement ajouter ses propres documents. Un médecin peut lire et modifier les données cliniques uniquement pendant une affectation active. Le rôle administrateur n'a pas accès à cette API métier.

Ressources : `record/`, `chronic-diseases/`, `allergies/`, `treatments/`, `consultations/`, `notes/` et `documents/`. Les collections acceptent la pagination ainsi que `patient_id` (médecin seulement), `date_from`, `date_to`, `status` et `ordering` lorsque le filtre s'applique. `PUT` et `DELETE` sont désactivés.

Les fichiers PDF, JPEG et PNG sont limités par `MEDICAL_DOCUMENT_MAX_SIZE` (10 Mio par défaut). Extension, type MIME déclaré et signature binaire sont contrôlés. Le nom de stockage est un UUID et n'est jamais renvoyé par l'API. Le contenu se télécharge exclusivement via `GET /api/medical-records/documents/{id}/download/`, après le même contrôle de propriété ou d'affectation active. Un antivirus pourra être branché dans `validate_medical_document_file` sans modifier l'API.

Les anciens champs texte redondants ont été renommés `legacy_*` par migration sans perte de données. Ils restent visibles en lecture seule pour assurer la transition vers les tables normalisées.

La spécification complète et les exemples de schémas sont disponibles dans Swagger (`/api/docs/`) et ReDoc (`/api/redoc/`).
