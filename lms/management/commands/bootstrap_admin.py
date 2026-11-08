import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a superuser from deployment environment variables if it does not exist."

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "").strip()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")

        if not username and not password:
            self.stdout.write("Admin bootstrap skipped; no admin credentials are configured.")
            return
        if not username or not password:
            raise CommandError(
                "Set both DJANGO_SUPERUSER_USERNAME and DJANGO_SUPERUSER_PASSWORD."
            )

        user_model = get_user_model()
        if user_model.objects.filter(**{user_model.USERNAME_FIELD: username}).exists():
            self.stdout.write("Admin already exists; no account or password was changed.")
            return

        user_model.objects.create_superuser(
            **{
                user_model.USERNAME_FIELD: username,
                "email": email,
                "password": password,
            }
        )
        self.stdout.write("Admin account created successfully.")
