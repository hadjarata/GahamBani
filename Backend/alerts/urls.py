from rest_framework.routers import SimpleRouter

from .views import MedicalAlertViewSet


router = SimpleRouter()
router.register('', MedicalAlertViewSet, basename='alert')
urlpatterns = router.urls
