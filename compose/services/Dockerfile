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
  apt-get install -y sudo curl && \
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

ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright/pw-browsers
RUN mkdir -p "$PLAYWRIGHT_BROWSERS_PATH" && chmod 777 "$PLAYWRIGHT_BROWSERS_PATH"

FROM app_base as development_image

RUN poetry install

RUN playwright install --with-deps chromium

COPY . .

CMD ["bash", "./compose/services/start-django.sh"]
# manage.py createsuperuser --noinput --username DJANGO_SUPERUSER_USERNAME --email DJANGO_SUPERUSER_EMAIL --password DJANGO_SUPERUSER_PASSWORD


# FROM app_base as prod_image

# ARG REPOSITORY_URL
# ARG COMMIT_HASH
# ARG PROJECT_NAME
# ARG NEW_RELIC_METADATA_REPOSITORY_URL=${REPOSITORY_URL}
# ARG NEW_RELIC_METADATA_COMMIT=${COMMIT_HASH}
# ARG PROJECT_NAME=${PROJECT_NAME}

# COPY --from=lacework_image /var/lib/lacework-backup /var/lib/lacework-backup

# RUN poetry install --only main

# COPY . .

# RUN mkdir -p /app/dist
# RUN chown -R $USERNAME /app/dist

# USER $USERNAME

# CMD ["bash", "./compose/services/web/startup-with-lw.sh"]
