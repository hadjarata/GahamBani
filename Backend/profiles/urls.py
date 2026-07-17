from django.urls import path

from .views import AssignmentsView, MeView, MyDoctorsView, MyPatientsView


app_name = 'profiles'

urlpatterns = [
    path('me/', MeView.as_view(), name='me'),
    path('my-patients/', MyPatientsView.as_view(), name='my-patients'),
    path('my-doctors/', MyDoctorsView.as_view(), name='my-doctors'),
    path('assignments/', AssignmentsView.as_view(), name='assignments'),
]
