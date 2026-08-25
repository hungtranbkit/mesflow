FROM python:3.13-slim-bookworm
ARG GIT_COMMIT=unknown
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Ho_Chi_Minh \
    MESFLOW_BUILD_COMMIT=$GIT_COMMIT
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates tzdata postgresql-client && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY app /app
COPY VERSION.txt /app/VERSION.txt
COPY scripts/docker-entrypoint.sh /usr/local/bin/mesflow-entrypoint
RUN chmod +x /usr/local/bin/mesflow-entrypoint
EXPOSE 8080
ENTRYPOINT ["mesflow-entrypoint"]
