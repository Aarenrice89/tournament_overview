# Development

- Use Python 3.12 and Poetry; the container installs dependencies with `poetry install --no-root`.
- Django commands use `tournament_overview.settings` and require environment values such as `DJANGO_SECRET_KEY` and PostgreSQL connection settings. Compose loads them from `compose/envs/.env`.
- The development Compose stack requires the external Docker network `proxy`; create it before starting Compose if absent: `docker network create proxy`.
- The devcontainer intentionally leaves the `api` container idle. Start Django manually with `bash compose/services/start-django.sh`, or run management commands with `poetry run python manage.py <command>`.

# Architecture

- `tournament_overview/settings.py` is the central configuration: PostgreSQL is required, Redis backs cache and Celery, and API authentication defaults to JWT or Basic authentication.
- Root routing is in `tournament_overview/urls.py`; the staff-only tournament UI is provided by `tournaments.urls` at `/`.
- Compose `setup` runs migrations, `create_default_admin`, and `collectstatic` before the API service. Celery worker and beat use `celery -A tournament_overview`.

# Verification

- Format Python with `poetry run black .`; Black uses 119-character lines and deliberately excludes `manage.py`, ASGI/WSGI files, and migrations.
- Sort imports with `poetry run isort .` (configured for Black compatibility).
- Lint with `poetry run flake8`.
- Run Django validation with `poetry run python manage.py check` after loading the required environment. The Compose `.env` contains shell metacharacters, so parse it with `python-dotenv` rather than sourcing it in Bash.
- No repository test suite or pytest dependency is currently configured; do not assume `pytest` is available.
