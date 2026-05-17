from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie


@ensure_csrf_cookie
def csrf_failure(request, reason=""):
    return render(request, "csrf_failure.html", {"reason": reason}, status=403)
