FROM python:3.13-slim-bullseye AS builder

ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libmariadb-dev-compat \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.13-slim-bullseye

ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1
ENV APP_HOME /app

WORKDIR $APP_HOME

COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn
COPY --from=builder /usr/local/bin/alembic /usr/local/bin/alembic

# Copy source code and Alembic configuration
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Copy entrypoint script
COPY docker-entrypoint.sh /app/
RUN chmod +x /app/docker-entrypoint.sh

RUN mkdir -p /app/src/hpc_drive/uploads

EXPOSE 7777

ENV PYTHONPATH=/app
ENV UPLOADS_DIR=/app/src/hpc_drive/uploads
ENV DATABASE_URL="sqlite:////app/data/drive.db"
ENV AUTH_SERVICE_ME_URL="http://auth_service:8082/api/v1/me"

ENTRYPOINT ["/app/docker-entrypoint.sh"]
