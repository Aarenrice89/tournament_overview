# Development

- Use Python 3.12 and Poetry. Docker development installs dependencies with `poetry install --no-root`.
- Django requires values from `compose/envs/.env`, including PostgreSQL and `DJANGO_SECRET_KEY`. Do not source this file in Bash because it contains shell metacharacters; use `python-dotenv` or run inside Compose.
- The development Compose stack requires the external `proxy` network: `docker network create proxy`. Its `setup` service migrates, runs `create_default_admin`, and collects static files; start Django in the `api` container with `bash compose/services/start-django.sh`.
- Production uses `compose/docker-compose.production.yml`; Caddy is the only public service. Create `compose/envs/.env.production` from its example, set `GHCR_IMAGE`, and never commit it. GitHub Actions publishes the API image to private GHCR; the pinned `nickfedor/watchtower:1.20.2` service updates only the labeled API container.

# Structure

- `/` is the role-aware application launcher. `tournaments` provides the staff-only tournament UI at `/tournaments/`; `coaches` owns invitation registration, coach work logs, and staff payroll at `/coaches/`. Django admin is at `/admin/`; public OpenAPI schema and Swagger UI are `/api/schema/` and `/api/docs/`.
- `TournamentRegistration` is the tournament-team join model. Its database constraints enforce one registration per tournament/team and the registered -> paid -> rosters status progression.
- `registration_opens_date`, `registration_closes_date`, and `end_date` may be `NULL`; preserve unknown dates instead of inventing values.
- Coach invitation emails use SMTP and `SITE_URL`; configure Google Workspace credentials and `DEFAULT_FROM_EMAIL` outside version control. Payroll and work-item rate snapshots must not be rewritten when current coach rates change. A paid `PayrollMonth` locks coach work changes for every coach; only staff may correct paid-month work.
- Initialize each new Central Time payroll month with `poetry run python manage.py initialize_current_payroll_month`; the command is idempotent for the Droplet cron job.

# Data Import

- Import Excel detail sheets with `poetry run python manage.py import_tournament_workbook [path]`. With no path, it reads `Copy 2026-2027 Tournament Chart.xlsx` from the repository root.
- The importer is repeat-safe: it updates tournaments by name and start date and registrations by tournament/team. Review warnings: invalid end dates are discarded and unparseable costs are stored as zero.

# Verification

- Run `poetry run black .`, then `poetry run isort .`; Black uses 119-character lines and excludes migrations plus `manage.py`/ASGI/WSGI entrypoints.
- Run `poetry run flake8` and, with the required environment loaded, `poetry run python manage.py check`. `scripts/adhoc_script.py` has existing flake8 violations.
- The repository uses Django's test runner, not pytest. Run focused suites with `poetry run python manage.py test tournaments` or `poetry run python manage.py test coaches` after loading the required environment.
