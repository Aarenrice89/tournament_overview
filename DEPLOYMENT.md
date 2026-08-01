# Production Deployment

The production API image is published to GitHub Container Registry whenever a commit is pushed to `main`. The image is private and Watchtower checks for a new `production` tag every five minutes.

## GitHub Setup

1. In the repository Settings, allow GitHub Actions workflows to read and write packages.
2. Push the workflow to `main` once. GitHub creates the package at `ghcr.io/<owner>/<repository>`.
3. In the package settings, keep package visibility private and connect it to this repository if GitHub did not do so automatically.

## Droplet Setup

1. Create a dedicated GitHub machine account or a classic personal access token with only `read:packages` access to this package.
2. Log in as the same host user that runs Docker Compose, then authenticate Docker:

   ```bash
   docker login ghcr.io -u <github-user> --password-stdin
   ```

3. Create `compose/envs/.env.production` from the example. Set `GHCR_IMAGE` to the lowercase `<github-owner>/<repository>` path used by GHCR, and provide the existing Django, PostgreSQL, Redis, and SMTP values.
4. Keep the production Compose file, Caddyfile, and environment file on the Droplet. The environment file is not stored in Git or included in the image.
5. Perform the initial deployment:

   ```bash
   docker compose --env-file compose/envs/.env.production -f compose/docker-compose.production.yml pull
   docker compose --env-file compose/envs/.env.production -f compose/docker-compose.production.yml up -d
   ```

6. Confirm Watchtower is running:

   ```bash
   docker compose --env-file compose/envs/.env.production -f compose/docker-compose.production.yml logs watchtower
   ```

## Releases

After the initial setup, a push to `main` publishes `:production` and an immutable `:sha-<commit>` image tag. The pinned `nickfedor/watchtower:1.20.2` service checks for updates every five minutes and recreates only the labeled API container.

The API startup command applies Django migrations and collects static files before starting Gunicorn. Keep schema migrations backward-compatible for automatic rollout. For destructive or non-reversible migrations, take a database backup and temporarily perform a controlled manual deployment instead.

Compose, Caddyfile, and environment-file changes are not deployed by Watchtower. Update those files on the Droplet and rerun `docker compose ... up -d` when they change.

## Monthly Payroll Initialization

Use the `initialize_current_payroll_month` command to initialize the current Central Time month. It is idempotent and can safely run more than once:

```bash
docker compose --env-file compose/envs/.env.production -f compose/docker-compose.production.yml exec -T api python manage.py initialize_current_payroll_month
```

Use a systemd timer on the Droplet to run the command at midnight Central Time on the first of every month. Unlike cron, `Persistent=true` runs a missed task after the Droplet returns online.

Create `/etc/systemd/system/midtnvbc-payroll-init.service`, replacing `/opt/midtnvbc` with the directory containing the Compose files:

```ini
[Unit]
Description=Initialize current coach payroll month

[Service]
Type=oneshot
WorkingDirectory=/opt/midtnvbc
ExecStart=/usr/bin/docker compose --env-file compose/envs/.env.production -f compose/docker-compose.production.yml exec -T api python manage.py initialize_current_payroll_month
```

Create `/etc/systemd/system/midtnvbc-payroll-init.timer`:

```ini
[Unit]
Description=Initialize coach payroll monthly

[Timer]
OnCalendar=*-*-01 00:00:00 America/Chicago
Persistent=true

[Install]
WantedBy=timers.target
```

Enable the timer:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now midtnvbc-payroll-init.timer
```

Check its next scheduled run and inspect execution logs with:

```bash
systemctl list-timers midtnvbc-payroll-init.timer
journalctl -u midtnvbc-payroll-init.service
```
