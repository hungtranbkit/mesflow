FROM python:3.12-slim
WORKDIR /srv
RUN pip install --no-cache-dir Flask==3.1.1 gunicorn==23.0.0
COPY services/public-support/ /srv/services/public-support/
WORKDIR /srv/services/public-support
USER 65534:65534
EXPOSE 8088
CMD ["gunicorn", "--bind", "0.0.0.0:8088", "--workers", "1", "--threads", "4", "--timeout", "30", "--access-logfile", "/dev/null", "server:app"]
