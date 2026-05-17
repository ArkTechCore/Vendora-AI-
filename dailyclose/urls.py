from django.urls import path

from .views import close_form, close_list, close_receipt

urlpatterns = [
    path("", close_list, name="daily_close_list"),
    path("new/", close_form, name="daily_close_create"),
    path("<int:pk>/receipt/", close_receipt, name="daily_close_receipt"),
]
