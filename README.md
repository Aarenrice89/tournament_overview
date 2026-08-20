# Mid TN VB Club Portal

Django application for Mid TN Volleyball Club tournament planning and coach payroll.

## Applications

- `/`: Role-aware portal launcher.
- `/tournaments/`: Staff-only tournament, team, registration, payment, and roster management.
- `/coaches/`: Coach work-log and payroll portal.
- `/coaches/admin/`: Staff payroll administration, coach compensation, invitations, and paid-month controls.
- `/admin/`: Django administration.
- `/api/schema/` and `/api/docs/`: Public OpenAPI schema and Swagger UI.

Staff users see the Tournament Overview and Payroll Admin applications. Coach users see Coach Payroll. Staff coaches see all available applications.

## Development

Requirements:

- Python 3.12 and Poetry for local commands.
- Docker and Docker Compose for the full development stack.
- An external Docker network named `proxy`.

Create the development environment file from the committed template and replace its placeholder secrets:

```bash
cp compose/envs/.env.example compose/envs/.env
docker network create proxy
docker compose -f compose/docker-compose.yml up --build
```

The development stack runs PostgreSQL, Redis, setup migrations, and Django. The application is exposed through the configured local proxy at `https://api.tournament-overview.localhost`.

Run Django commands inside the API container, or load environment values with `python-dotenv`. Do not source `compose/envs/.env` directly in Bash.

```bash
docker compose -f compose/docker-compose.yml exec api python manage.py shell
docker compose -f compose/docker-compose.yml exec api python manage.py migrate
```

## Coach Payroll

Staff create one-week coach invitations from `/coaches/admin/invitations/`. Invitation emails use Resend's API; configure `RESEND_API_KEY`, a `DEFAULT_FROM_EMAIL` sender on a verified Resend domain, and `SITE_URL` outside version control.

Coach work supports hourly activities, tournaments, and private lessons. Payroll totals snapshot current rates when work or a monthly payroll record is created. Marking a `PayrollMonth` paid locks coach edits for all coaches in that month; staff can reopen the month or make corrections.

## Tournament Import

Import Excel detail sheets with:

```bash
poetry run python manage.py import_tournament_workbook [path]
```

With no path, the importer reads `Copy 2026-2027 Tournament Chart.xlsx` from the repository root. Imports are repeat-safe by tournament name/start date and registration tournament/team.

## Verification

```bash
poetry run black .
poetry run isort .
poetry run flake8
poetry run python manage.py check
poetry run python manage.py test tournaments coaches tournament_overview
```

## Production

Production uses `compose/docker-compose.production.yml` with Caddy as the only public service. GitHub Actions publishes the API image to private GitHub Container Registry after pushes to `main`; the pinned `nickfedor/watchtower:1.20.2` service updates only the labeled API container.

Create production configuration from `compose/envs/.env.production.example`, set all secrets and `GHCR_IMAGE`, then follow [DEPLOYMENT.md](DEPLOYMENT.md) for GitHub and DigitalOcean setup. Never commit production environment files.
