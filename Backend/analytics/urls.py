from django.urls import path

from .views import AlertsView, BloodGlucoseView, BloodPressureView, Hba1cView, SummaryView, TrendsView


app_name = 'analytics'

urlpatterns = [
    path('summary/', SummaryView.as_view(), name='summary'),
    path('blood-pressure/', BloodPressureView.as_view(), name='blood-pressure'),
    path('blood-glucose/', BloodGlucoseView.as_view(), name='blood-glucose'),
    path('hba1c/', Hba1cView.as_view(), name='hba1c'),
    path('alerts/', AlertsView.as_view(), name='alerts'),
    path('trends/', TrendsView.as_view(), name='trends'),
]
