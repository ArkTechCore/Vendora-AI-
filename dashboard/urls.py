from django.urls import path

from .views import dashboard, settings_hub

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("settings/", settings_hub, name="settings_hub"),
]
