#!/bin/bash
set -eu

while python manage.py showmigrations | grep '\[ \]' &> /dev/null; do
    echo "Waiting for all migrations"
    sleep 3
done

python manage.py collectstatic --no-input

WEBSERVER="${WEBSERVER:-DJANGO}"

if [ "${WEBSERVER^^}" = "DJANGO" ]; then
    echo "WEBSERVER config set to DJANGO"
    python manage.py runserver 0.0.0.0:8080
else
    gunicorn --reload yosemite_scraper.wsgi
fi