FROM postgres:17.10-alpine
ARG PATRONI_VERSION=4.1.5
RUN apk add --no-cache python3 py3-pip curl jq tzdata \
 && pip3 install --break-system-packages --no-cache-dir "patroni[psycopg3,etcd3]==${PATRONI_VERSION}" \
 && patroni --version \
 && postgres --version \
 && pg_rewind --version \
 && pg_basebackup --version
USER postgres
ENTRYPOINT ["patroni"]
CMD ["/etc/patroni/patroni.yml"]
