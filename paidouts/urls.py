from django.urls import path

from .views import paidout_form, paidout_list

urlpatterns = [
    path("", paidout_list, name="paidout_list"),
    path("new/", paidout_form, name="paidout_create"),
]
