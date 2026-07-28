# Development

- Use Python 3.12 and Poetry. The development image installs dependencies with `poetry install --no-root`.
- Django commands need the PostgreSQL and secret-key values in `compose/envs/.env`. Do not source that file in Bash; it contains shell metacharacters. Parse it with `python-dotenv` or run commands in the Compose environment.
- The Compose stack requires an external `proxy` network: `docker network create proxy`. The devcontainer leaves `api` idle; start Django there with `bash compose/services/start-django.sh`.
- Compose `setup` applies migrations, runs `create_default_admin`, and collects static files before the app starts.
- Production uses `compose/docker-compose.production.yml` with Caddy as the only public service. Create, but never commit, `compose/envs/.env.production` from its example.

# Structure

- `tournaments` is the only custom app. Its staff-only management UI is mounted at `/`; root API schema and Swagger routes are `/api/schema/` and `/api/docs/`.
- `TournamentRegistration` is the tournament-team join model. Its database constraints enforce one registration per tournament/team and the registered -> paid -> rosters status progression.
- `registration_opens_date`, `registration_closes_date`, and `end_date` may be `NULL`; preserve unknown dates instead of inventing values.

# Data Import

- Import Excel detail sheets with `poetry run python manage.py import_tournament_workbook [path]`. Without a path, it reads `Copy 2026-2027 Tournament Chart.xlsx` from the repository root.
- The importer is repeat-safe: it updates tournaments by name and start date and updates registrations by tournament/team. Review its warnings for unparseable costs and invalid dates.

# Verification

- Run `poetry run black .`, then `poetry run isort .`; Black uses 119-character lines and excludes migrations plus `manage.py`/ASGI/WSGI entrypoints.
- Run `poetry run flake8` and Django validation with `poetry run python manage.py check` after loading the required environment. `scripts/adhoc_script.py` currently has existing flake8 violations.
- The repository uses Django's test runner, not pytest. Run the focused app suite with `poetry run python manage.py test tournaments` after loading the required environment.
