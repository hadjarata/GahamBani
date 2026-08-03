# Deep link de réinitialisation du mot de passe

Expo Router expose automatiquement la route mobile `/reset-password/confirm`.
Le backend ajoute les paramètres `uid` et `token` à la valeur de
`FRONTEND_RESET_PASSWORD_URL`.

## Format retenu

Pour un development build ou une application native installée :

```text
gahambanimobile:///reset-password/confirm?uid=<uid>&token=<token>
```

Pour Expo Go, l’URL dépend de l’adresse du serveur de développement et n’est
pas stable. Il faut tester avec une URL de la forme :

```text
exp://<adresse-metro>/--/reset-password/confirm?uid=<uid>&token=<token>
```

## Production

Le domaine HTTPS de production n’est pas encore défini dans l’application.
Quand il sera connu, configurer ce domaine comme Android App Link et iOS
Universal Link, publier les fichiers d’association de plateforme, puis définir :

```text
FRONTEND_RESET_PASSWORD_URL=https://<domaine>/reset-password/confirm
```

Ne pas utiliser la valeur locale actuelle du backend (`localhost:3000`) sur un
téléphone. Le schéma personnalisé suffit aux development builds, mais un lien
HTTPS associé est préférable en production et offre un repli web si l’app n’est
pas installée.
