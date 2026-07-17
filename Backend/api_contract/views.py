from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from config.version import API_VERSION

from .serializers import HealthSerializer


class HealthView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    http_method_names = ('get', 'head', 'options')

    @extend_schema(
        tags=['Technical'], operation_id='v1_health_retrieve',
        summary='Vérifier la disponibilité publique de l’API',
        description='Ne vérifie ni ne révèle la base de données, les dépendances ou l’environnement.',
        auth=[], responses={200: HealthSerializer},
    )
    def get(self, request):
        return Response({'status': 'ok', 'version': API_VERSION})
