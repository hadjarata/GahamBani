from django.urls import include, path


urlpatterns = [
    path('api/auth/', include('accounts.urls')),
    path('api/profiles/', include('profiles.urls')),
    path('api/monitoring/', include('monitoring.urls')),
    path('api/medical-records/', include('medical_records.urls')),
    path('api/alerts/', include('alerts.urls')),
    path('api/notifications/', include('notifications.urls')),
    path('api/analytics/', include('analytics.urls')),
]
