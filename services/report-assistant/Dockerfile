FROM python:3.12-slim
WORKDIR /srv
RUN apt-get update && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir Flask==3.1.1 gunicorn==23.0.0 openpyxl==3.1.5 weasyprint==66.0
COPY services/report-assistant/ /srv/
USER 65534:65534
EXPOSE 8089
CMD ["gunicorn", "--bind", "0.0.0.0:8089", "--workers", "1", "--threads", "4", "--timeout", "35", "--access-logfile", "/dev/null", "server:app"]
