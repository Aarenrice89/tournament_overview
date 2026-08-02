FROM python:3.12-slim-bullseye as app_base

ENV PYTHONUNBUFFERED=1
# ENV NEW_RELIC_CONFIG_FILE=/app/newrelic.ini

ARG USERNAME=app-user
ARG USER_UID=1000
ARG USER_GID=$USER_UID

RUN groupadd --gid $USER_GID $USERNAME && \
  useradd --uid $USER_UID --gid $USER_GID -m $USERNAME && \
  # install packages
   apt-get update && \
   apt-get install -y sudo curl ca-certificates gnupg && \
   curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg && \
   echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt bullseye-pgdg main" > /etc/apt/sources.list.d/pgdg.list && \
   apt-get update && \
   apt-get install -y postgresql-client-16 && \
  rm -rf /var/lib/apt/lists/* && \
  # add user to sudoers
  echo $USERNAME  ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME && \
  chmod 0440 /etc/sudoers.d/$USERNAME

WORKDIR /app

RUN pip install poetry lockfile

RUN poetry config virtualenvs.create false

# RUN \
#   --mount=type=secret,id=gitlab,required=true,target=/app/gitlab \
#   poetry config -- http-basic.gitlab gitlab-ci-token $(cat /app/gitlab)

COPY pyproject.toml poetry.lock /app/

FROM app_base as development_image

RUN poetry install --no-root
COPY . .

CMD ["bash", "./compose/services/start-django.sh"]
# manage.py createsuperuser --noinput --username DJANGO_SUPERUSER_USERNAME --email DJANGO_SUPERUSER_EMAIL --password DJANGO_SUPERUSER_PASSWORD


FROM app_base as production_image

RUN poetry install --only main --no-root
COPY . .

CMD ["bash", "./compose/services/start-production.sh"]
