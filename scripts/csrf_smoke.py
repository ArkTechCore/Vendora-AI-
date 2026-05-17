import re

from django.conf import settings
from django.test import Client as TestClient

from accounts.models import User
from clients.models import Client


def token_from(html):
    match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)
    if not match:
        raise RuntimeError("No CSRF token found in response.")
    return match.group(1)


quickstop = Client.objects.get(name__iexact="Quick stop")
User.objects.filter(username__in=["csrf_super", "csrf_owner"]).delete()
User.objects.create_superuser("csrf_super", "csrf_super@example.com", "Testpass123!")
User.objects.create_user(
    "csrf_owner",
    "csrf_owner@example.com",
    "Testpass123!",
    role="client_owner",
    client=quickstop,
)

client = TestClient(enforce_csrf_checks=True)

response = client.get("/accounts/login/")
print("login_get", response.status_code, settings.CSRF_COOKIE_NAME in client.cookies)
csrf = token_from(response.content.decode())
response = client.post("/accounts/login/", {"username": "csrf_super", "password": "Testpass123!", "csrfmiddlewaretoken": csrf})
print("super_login", response.status_code)

response = client.get("/")
csrf = token_from(response.content.decode())
response = client.post("/accounts/logout/", {"csrfmiddlewaretoken": csrf})
print("logout", response.status_code, response.url)

response = client.get("/accounts/login/")
print("login_get_2", response.status_code, settings.CSRF_COOKIE_NAME in client.cookies)
csrf = token_from(response.content.decode())
response = client.post("/accounts/login/", {"username": "csrf_owner", "password": "Testpass123!", "csrfmiddlewaretoken": csrf})
print("owner_login", response.status_code)

User.objects.filter(username__in=["csrf_super", "csrf_owner"]).delete()
