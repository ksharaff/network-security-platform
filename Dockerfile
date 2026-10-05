FROM python:3.12-slim

# PYTHONDONTWRITEBYTECODE: skip .pyc files, pointless in a container.
# PYTHONUNBUFFERED: logs go straight to stdout instead of buffering.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /code

# Copy requirements BEFORE source code so Docker's layer cache reuses
# the slow pip install whenever only application code changed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Alembic needs its config file and the migration scripts at runtime.
COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

EXPOSE 8000

# On every start: bring the schema up to date, then run the server.
#   sh -c        lets one CMD run two commands.
#   &&           runs uvicorn only if the migration succeeded. If it fails,
#                the container exits and the failure shows in the logs,
#                instead of serving an API on a broken schema.
#   exec         replaces the shell with uvicorn, so uvicorn receives the
#                stop signal from `docker compose stop` and shuts down cleanly.
# "upgrade head" is idempotent: when the schema is already current it
# does nothing, so restarts are safe.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]