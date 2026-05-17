from .models import AuditLog


def log_audit(user, action, message="", instance=None, client=None, store=None, safe_for_platform=False):
    if instance is not None:
        client = client or getattr(instance, "client", None) or getattr(getattr(instance, "store", None), "client", None)
        store = store or getattr(instance, "store", None)
    return AuditLog.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        client=client,
        store=store,
        action=action,
        model_name=instance.__class__.__name__ if instance is not None else "",
        object_id=str(instance.pk) if instance is not None and instance.pk else "",
        message=message,
        safe_for_platform=safe_for_platform,
    )
