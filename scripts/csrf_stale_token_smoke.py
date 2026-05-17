import re

from django.test import Client as TestClient

from accounts.models import User
from clients.models import Client


def token_from(html):
    match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)
    if not match:
        raise RuntimeError("No CSRF token found.")
    return match.group(1)


quickstop = Client.objects.get(name__iexact="Quick stop")
User.objects.filter(username__in=["csrf_stale_super", "csrf_stale_owner"]).delete()
User.objects.create_superuser("csrf_stale_super", "csrf_stale_super@example.com", "Testpass123!")
User.objects.create_user(
    "csrf_stale_owner",
    "csrf_stale_owner@example.com",
    "Testpass123!",
    role="client_owner",
    client=quickstop,
)

client = TestClient(enforce_csrf_checks=True)

response = client.get("/accounts/login/")
old_token = token_from(response.content.decode())
response = client.post("/accounts/login/", {"username": "csrf_stale_super", "password": "Testpass123!", "csrfmiddlewaretoken": old_token})
print("super_login", response.status_code)

response = client.get("/")
logout_token = token_from(response.content.decode())
response = client.post("/accounts/logout/", {"csrfmiddlewaretoken": logout_token})
print("logout", response.status_code)

response = client.get("/accounts/login/")
fresh_cookie_token = client.cookies["csrftoken"].value
response = client.post(
    "/accounts/login/",
    {"username": "csrf_stale_owner", "password": "Testpass123!", "csrfmiddlewaretoken": old_token},
)
print("stale_token_login", response.status_code)

response = client.post(
    "/accounts/login/",
    {"username": "csrf_stale_owner", "password": "Testpass123!", "csrfmiddlewaretoken": fresh_cookie_token},
)
print("refreshed_token_login", response.status_code)

User.objects.filter(username__in=["csrf_stale_super", "csrf_stale_owner"]).delete()
