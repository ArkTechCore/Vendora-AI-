from django.apps import AppConfig
from django.conf import settings


class AiAuditorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ai_auditor"
    verbose_name = "AI Restaurant Auditor"

    def ready(self):
        if getattr(settings, "MONGODB_URI", ""):
            from vendoraops.mongodb import log_mongodb_startup_status

            log_mongodb_startup_status()
