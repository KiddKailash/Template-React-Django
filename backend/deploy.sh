#!/bin/bash
# Fallback deploy script (e.g. Heroku/Procfile-style). The Pi deployment path
# uses docker-compose + the deploy.yml workflow, not this script.

set -e

echo "Running migrations..."
uv run python manage.py migrate --noinput

echo "Creating superuser if DJANGO_SUPERUSER_PASSWORD is set..."
uv run python manage.py shell << 'END'
from django.contrib.auth import get_user_model
import os

User = get_user_model()
username = os.getenv('DJANGO_SUPERUSER_USERNAME', 'admin')
email = os.getenv('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
password = os.getenv('DJANGO_SUPERUSER_PASSWORD')

if password:
    if not User.objects.filter(username=username).exists():
        print(f"Creating superuser {username}")
        User.objects.create_superuser(username, email, password)
    else:
        print(f"Superuser {username} already exists")
else:
    print("DJANGO_SUPERUSER_PASSWORD not set, skipping superuser creation")
END

echo "Starting Gunicorn..."
uv run gunicorn config.wsgi:application --timeout 60 --graceful-timeout 30
