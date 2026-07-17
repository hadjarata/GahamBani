# Déploiement du backend en staging

Le staging utilise `config.settings.staging`, hérite des protections de production
et ne doit contenir que des données fictives. Il exige Python 3.13 et PostgreSQL
16 (PostgreSQL 14 minimum recommandé). La base, son utilisateur et ses sauvegardes
doivent être distincts du développement et de la production. Utiliser une
connexion TLS (`DATABASE_SSLMODE=require`, ou `verify-full` lorsque l’hébergeur
fournit les certificats).

## Préparation

Définir les variables décrites dans `.env.example` dans le gestionnaire de
secrets de l’hébergeur. Ne jamais versionner le fichier d’environnement réel.
Les hosts, origines CSRF et origines CORS doivent être des listes explicites en
HTTPS. Une application Flutter native ne nécessite pas d’assouplissement CORS;
ajouter une origine uniquement pour Swagger ou un client web réellement hébergé.

Le stockage local de `MEDIA_ROOT` est éphémère et n’est pas un stockage durable
de documents médicaux. Avant tout usage persistant, monter un volume sauvegardé
ou intégrer ultérieurement un stockage objet privé. Les fichiers doivent rester
servis par les vues authentifiées de l’application.

## Vérification et release

Exécuter ces commandes dans une étape de release unique, avant de démarrer les
instances applicatives :

```bash
python manage.py check --deploy --settings=config.settings.staging
python manage.py migrate --plan --settings=config.settings.staging
python manage.py migrate --noinput --settings=config.settings.staging
python manage.py collectstatic --noinput --settings=config.settings.staging
```

Puis démarrer le service sans relancer les migrations simultanément :

```bash
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --access-logfile - --error-logfile -
```

Vérifier ensuite `GET /api/v1/health/` et le contrat OpenAPI versionné. Le health
check reste volontairement minimal et ne révèle aucun détail de base de données.

Les logs vont vers la console au niveau `INFO` avec un request ID. Ne jamais
journaliser corps de requête médical, notes, documents, mots de passe, JWT,
cookies, en-tête `Authorization` ou secrets.

## Retour arrière

Sauvegarder la base avant toute migration. Un rollback applicatif consiste à
redéployer l’artefact précédent, puis à vérifier le health check. Les migrations
destructives ne sont généralement pas réversibles automatiquement : examiner le
plan et préparer une migration corrective ou restaurer une sauvegarde validée.

`seed_demo_data` reste interdit en staging. Créer les comptes de test fictifs par
une procédure administrative contrôlée (`createsuperuser`, puis l’admin Django),
avec des identifiants propres au staging et une rotation après les essais.

