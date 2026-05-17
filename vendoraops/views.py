from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie

from .mongodb import ping_mongodb


@ensure_csrf_cookie
def csrf_failure(request, reason=""):
    return render(request, "csrf_failure.html", {"reason": reason}, status=403)


def mongodb_health(request):
    ok, message = ping_mongodb()
    status_code = 200 if ok else 503
    return JsonResponse({"status": "ok" if ok else "failed", "message": message}, status=status_code)
