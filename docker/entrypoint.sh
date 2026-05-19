#!/bin/sh
set -e

echo "Waiting for PostgreSQL..."

while ! nc -z ssod_auth_db 5432; do
  sleep 1
done

echo "PostgreSQL is available."

python manage.py migrate --noinput
python manage.py collectstatic --noinput


exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 2 \
  --timeout 60
