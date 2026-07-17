from rest_framework.routers import SimpleRouter

from .views import BloodGlucoseViewSet, BloodPressureViewSet


router = SimpleRouter()
router.register('blood-pressure', BloodPressureViewSet, basename='blood-pressure')
router.register('blood-glucose', BloodGlucoseViewSet, basename='blood-glucose')

urlpatterns = router.urls
