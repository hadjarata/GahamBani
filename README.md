# GahamBani

Backend Django REST Framework de GahamBani. L’API stable est publiée sous
`/api/v1/`; sa documentation et son contrat sont décrits dans
[Backend/docs/api-v1.md](Backend/docs/api-v1.md).

## Vérifications du backend

Depuis `Backend` :

```bash
python manage.py test --settings=config.settings.test
python manage.py spectacular --validate --settings=config.settings.test
python manage.py spectacular --validate --file openapi-v1.yaml --settings=config.settings.test
```

Sous Windows, `Backend/scripts/check_backend.ps1` reproduit les contrôles
principaux de la CI. Le workflow GitHub Actions vérifie Django, les migrations
sur une base PostgreSQL vide, tous les tests, le snapshot OpenAPI, les
dépendances installées et la configuration de production.

Voir la [procédure de staging](Backend/docs/staging-deployment.md) avant toute
release. Aucun déploiement automatique n’est configuré dans ce dépôt.
