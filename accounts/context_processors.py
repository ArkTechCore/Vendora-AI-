from django.db import models

from .models import ClientMessage, ClientMessageRead


def unread_messages(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"unread_message_count": 0}
    if user.is_super_admin():
        visible = ClientMessage.objects.all()
    else:
        visible = ClientMessage.objects.filter(
            models.Q(audience=ClientMessage.ALL_CLIENTS)
            | models.Q(audience=ClientMessage.CLIENT, client=user.client)
            | models.Q(audience=ClientMessage.PLATFORM, client=user.client)
        )
    read_ids = ClientMessageRead.objects.filter(user=user).values("message_id")
    count = visible.exclude(sender=user).exclude(id__in=read_ids).count()
    return {"unread_message_count": count}
