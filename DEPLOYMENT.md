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

## Database Backups

Database backups use PostgreSQL custom archives uploaded to AWS S3. Provision a private S3 bucket before enabling
the job. Enable bucket versioning, default encryption, and Object Lock when creating the bucket. Use S3 lifecycle
rules for the following prefixes. The ready-to-apply lifecycle configuration is at
`compose/aws/database-backup-lifecycle.json`; replace the bucket placeholder in
`compose/aws/database-backup-iam-policy.json` before assigning it to the server's IAM principal.

| Prefix | Retention |
| --- | --- |
| `postgres/daily/` | 30 days |
| `postgres/weekly/` | 13 weeks |
| `postgres/monthly/` | 24 months |
| `postgres/yearly/` | 7 years |
| `postgres/pre-restore/` | 30 days |
| `postgres/known-good/` | Manual review; no automatic expiry |

The backup command creates daily archives and copies the first successful archive of each Central Time week, month,
and year into the corresponding retention prefix. S3 lifecycle policies, rather than the application, expire old
archives. Configure the `AWS_REGION`, `DATABASE_BACKUP_S3_BUCKET`, `DATABASE_BACKUP_S3_PREFIX`, and, if used,
`DATABASE_BACKUP_S3_KMS_KEY_ID` values in `compose/envs/.env.production`. Provide the API container with AWS
credentials restricted to this bucket; do not commit those credentials.

Install the committed systemd unit files, replacing `/opt/midtnvbc` with the directory containing the Compose files:

```bash
sudo cp compose/systemd/midtnvbc-database-backup.service /etc/systemd/system/
sudo cp compose/systemd/midtnvbc-database-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now midtnvbc-database-backup.timer
```

The timer runs at midnight Central Time and uses `Persistent=true` to run a missed backup after the host returns.
Run a backup manually or inspect the timer with:

```bash
docker compose --env-file compose/envs/.env.production -f compose/docker-compose.production.yml run --rm --no-deps api python manage.py backup_database
systemctl list-timers midtnvbc-database-backup.timer
journalctl -u midtnvbc-database-backup.service
```

Promote a verified archive after an important import, reconciliation, or other trusted milestone. Known-good
archives are not subject to normal expiration:

```bash
docker compose --env-file compose/envs/.env.production -f compose/docker-compose.production.yml run --rm --no-deps api python manage.py promote_database_backup postgres/monthly/2026/08/01/tournament_overview-20260801T050000Z.dump
```

Restoring replaces the live database. Run it only from the host with the committed wrapper, which stops the API,
creates an emergency pre-restore backup, verifies the selected archive checksum, restores it, and starts the API
again only after success:

```bash
sudo bash compose/services/restore-database.sh postgres/known-good/2026/08/01/tournament_overview-20260801T050000Z.dump
```

If a restore fails, the wrapper leaves the API stopped to avoid serving a partially restored database. Test a restore
to an isolated PostgreSQL database at least monthly.
