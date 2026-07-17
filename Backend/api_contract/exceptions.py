from rest_framework.exceptions import APIException


class Conflict(APIException):
    status_code = 409
    default_detail = 'La ressource est en conflit avec l’état actuel.'
    default_code = 'conflict'


class BusinessRuleViolation(APIException):
    status_code = 400
    default_detail = 'Une règle métier empêche cette opération.'
    default_code = 'business_rule_violation'


class ProfileMissing(APIException):
    status_code = 404
    default_detail = 'Le profil métier requis est manquant.'
    default_code = 'profile_missing'


class ProfileCreationFailed(APIException):
    status_code = 500
    default_detail = 'Le profil patient n’a pas pu être créé.'
    default_code = 'profile_creation_failed'
