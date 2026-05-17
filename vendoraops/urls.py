"""
URL configuration for vendoraops project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from health_check.views import HealthCheckView
from ai_auditor import views as ai_auditor_views
from .views import mongodb_health

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', HealthCheckView.as_view(), name='health_check'),
    path('health/mongodb/', mongodb_health, name='mongodb_health'),
    path('', include('dashboard.urls')),
    path('accounts/', include('accounts.urls')),
    path('clients/', include('clients.urls')),
    path('stores/', include('stores.urls')),
    path('inventory/', include('inventory.urls')),
    path('paid-outs/', include('paidouts.urls')),
    path('daily-close/', include('dailyclose.urls')),
    path('pos/', include('pos_integrations.urls')),
    path('reports/', include('reports.urls')),
    path('ai/', include('ai_auditor.urls')),
    path('api/ai/analyze', ai_auditor_views.analyze_api, name='ai_analyze_root'),
    path('api/ai/investigate', ai_auditor_views.investigate_api, name='ai_investigate_root'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
