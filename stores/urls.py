from django.urls import path

from .views import store_form, store_list

urlpatterns = [
    path("", store_list, name="store_list"),
    path("new/", store_form, name="store_create"),
    path("<int:pk>/edit/", store_form, name="store_edit"),
]
