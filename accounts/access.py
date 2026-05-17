from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def role_required(*roles):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            user = request.user
            if user.is_super_admin() or user.role in roles:
                return view_func(request, *args, **kwargs)
            messages.error(request, "You do not have access to that page.")
            return redirect("dashboard")

        return wrapped

    return decorator


def permission_required(permission):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if request.user.has_manager_permission(permission):
                return view_func(request, *args, **kwargs)
            messages.error(request, "Your owner has not enabled that permission for your manager login.")
            return redirect("dashboard")

        return wrapped

    return decorator


def can_manage_client(user, client):
    if user.is_super_admin():
        return True
    return user.is_client_owner() and user.client_id == client.id


def store_scope(user):
    if user.is_super_admin():
        return {}
    if user.is_client_owner():
        return {"client": user.client}
    return {"id": user.store_id}
