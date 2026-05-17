from django.urls import path

from .views import client_form, client_list, client_status

urlpatterns = [
    path("", client_list, name="client_list"),
    path("new/", client_form, name="client_create"),
    path("<int:pk>/edit/", client_form, name="client_edit"),
    path("<int:pk>/status/<str:status>/", client_status, name="client_status"),
]
