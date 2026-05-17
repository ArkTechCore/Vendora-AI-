from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update the platform super admin login."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="mohammed")
        parser.add_argument("--password", default="Mohammed@1339")

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"]
        password = options["password"]
        user, _ = User.objects.get_or_create(username=username)
        user.role = User.SUPER_ADMIN
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Super admin ready: {username}"))
