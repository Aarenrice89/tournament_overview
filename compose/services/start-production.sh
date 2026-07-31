#!/bin/bash
set -eu

python manage.py migrate --noinput
python manage.py collectstatic --no-input
exec gunicorn tournament_overview.wsgi:application --bind 0.0.0.0:8080 --workers 2
