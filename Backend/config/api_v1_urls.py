from django.urls import include, path

from api_contract.views import HealthView


app_name = 'api-v1'

urlpatterns = [
    path('health/', HealthView.as_view(), name='health'),
    path('auth/', include('accounts.v1_urls')),
    path('profiles/', include('profiles.urls')),
    path('monitoring/', include('monitoring.urls')),
    path('medical-records/', include('medical_records.urls')),
    path('alerts/', include('alerts.urls')),
    path('notifications/', include('notifications.urls')),
    path('analytics/', include('analytics.urls')),
]
