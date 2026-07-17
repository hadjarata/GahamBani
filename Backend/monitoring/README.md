# Domaine monitoring

Les tensions sont stockées en mmHg et la fréquence cardiaque en bpm. La
glycémie conserve l'unité explicitement fournie (`G_PER_L` ou `MG_PER_DL`) et
aucune conversion silencieuse n'est effectuée.

Le patient actif peut créer, lire et corriger ses propres mesures. La source
des créations API est forcée à `MANUAL`. Un médecin est strictement en lecture
seule et uniquement pour ses affectations actives. Le rôle `ADMIN` n'accorde
aucun accès à cette API.

La suppression physique et le remplacement du propriétaire sont interdits par
l'API. Un journal d'audit des corrections devra être ajouté avant d'élargir les
droits d'écriture ou d'introduire des processus administratifs de suppression.
