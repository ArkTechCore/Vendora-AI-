import time

from django.test import Client as TestClient

from accounts.models import User


def measure(label, user, paths):
    client = TestClient()
    client.force_login(user)
    print(label)
    for path in paths:
        start = time.perf_counter()
        response = client.get(path)
        elapsed = (time.perf_counter() - start) * 1000
        print(f"  {path}: {response.status_code} {elapsed:.1f}ms {len(response.content)} bytes")


super_admin = User.objects.filter(is_superuser=True).first()
owner = User.objects.filter(role=User.CLIENT_OWNER, client__name__iexact="Kabeb Station").first() or User.objects.filter(role=User.CLIENT_OWNER).first()

measure("super_admin", super_admin, ["/", "/reports/", "/reports/?month=2026-05", "/reports/pdf/?report_type=platform"])
measure("client_owner", owner, ["/", "/reports/", "/reports/?month=2026-05", "/paid-outs/", "/inventory/purchases/", "/daily-close/"])
