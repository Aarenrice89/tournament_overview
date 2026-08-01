#!/bin/bash

python manage.py migrate --noinput

python manage.py runscript create_default_admin

python manage.py collectstatic --no-input
