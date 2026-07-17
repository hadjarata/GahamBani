# Journal d'audit médical

`medical_audit` conserve les lectures sensibles, listes, créations, modifications, uploads et téléchargements réalisés dans `monitoring` et `medical_records`. Il n'expose aucune route REST : la consultation se fait uniquement dans l'admin Django, en lecture seule, par un superutilisateur autorisé.

Les événements sont append-only. Le modèle, son QuerySet et l'admin refusent modification et suppression dans le fonctionnement normal. Les références acteur/patient utilisent `SET_NULL`, tandis que leurs UUID historiques restent conservés. Les ressources métier sont référencées par type et UUID sans cascade.

Les mots de passe, JWT, tokens, en-têtes Authorization, cookies, secrets, corps de requête, texte intégral des notes, contenu binaire et chemins de stockage sont exclus. Les valeurs avant/après sont limitées aux mesures numériques et champs courts explicitement autorisés. Les erreurs d'écriture d'audit alimentent uniquement le journal technique et ne bloquent pas l'opération médicale.

L'adresse IP vient de `REMOTE_ADDR` par défaut. `X-Forwarded-For` n'est utilisé que si `DRF_NUM_PROXIES` déclare explicitement le nombre de proxies contrôlés. Un UUID de corrélation validé ou généré est renvoyé dans `X-Request-ID`; le middleware ne lit jamais le corps.

Les refus 401, UUID inexistants et objets masqués ne sont pas enregistrés afin d'éviter bruit, fausses attributions et fuite d'existence. Aucun moteur de purge n'est actif. Une politique réglementaire de rétention, un archivage signé et une exportation SIEM devront être définis avant la production à grande échelle.
