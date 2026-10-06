#!/bin/bash
# Выполняется один раз при первом запуске контейнера PostgreSQL (пустой том).
# Создаёт базы и роли: хранилище проекта, метаданные Airflow, метаданные Superset,
# а также роль только для чтения витрин — под ней Superset подключается к хранилищу.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-SQL
    CREATE ROLE ${WAREHOUSE_USER} LOGIN PASSWORD '${WAREHOUSE_PASSWORD}';
    CREATE DATABASE ${WAREHOUSE_DB} OWNER ${WAREHOUSE_USER};

    CREATE ROLE airflow LOGIN PASSWORD '${AIRFLOW_DB_PASSWORD}';
    CREATE DATABASE airflow OWNER airflow;

    CREATE ROLE superset LOGIN PASSWORD '${SUPERSET_DB_PASSWORD}';
    CREATE DATABASE superset OWNER superset;

    CREATE ROLE ${BI_READER_USER} LOGIN PASSWORD '${BI_READER_PASSWORD}';
SQL

# Права читателя BI: только схемы витрин и служебная meta (для операционного дашборда).
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$WAREHOUSE_DB" <<-SQL
    GRANT CONNECT ON DATABASE ${WAREHOUSE_DB} TO ${BI_READER_USER};
    SET ROLE ${WAREHOUSE_USER};
    CREATE SCHEMA IF NOT EXISTS marts;
    CREATE SCHEMA IF NOT EXISTS meta;
    GRANT USAGE ON SCHEMA marts, meta TO ${BI_READER_USER};
    ALTER DEFAULT PRIVILEGES IN SCHEMA marts GRANT SELECT ON TABLES TO ${BI_READER_USER};
    ALTER DEFAULT PRIVILEGES IN SCHEMA meta  GRANT SELECT ON TABLES TO ${BI_READER_USER};
SQL
