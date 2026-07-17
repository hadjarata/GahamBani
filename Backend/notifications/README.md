# Notifications in-app

Une alerte représente une situation médicale; une notification est le message court présenté à un destinataire. Ce MVP stocke uniquement des notifications internes en base. Aucun SMS, push, e-mail médical, Firebase, Celery ou canal externe n'est utilisé.

La création d'une alerte notifie le patient actif et chaque médecin actif actuellement affecté. `ACKNOWLEDGE`, `RESOLVE` et `DISMISS` notifient uniquement le patient avec un message neutre. Les valeurs médicales exactes, motifs internes, notes, secrets et identifiants d'autres utilisateurs ne sont jamais copiés dans le contenu public.

L'idempotence repose sur destinataire + événement + type/UUID source. Une notification commence non lue; `read` et `read-all` sont irréversibles dans ce MVP et idempotents. Chaque utilisateur ne consulte que ses propres notifications. Il n'existe aucune création API, aucun PATCH générique, aucun PUT ni DELETE.

Les notifications ne sont pas un registre réglementaire permanent. Aucune purge n'est encore active; une politique de rétention produit devra être définie séparément de celle du journal `medical_audit`. Les futurs canaux externes devront être asynchrones et ne pas bloquer les transactions médicales.
