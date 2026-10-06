FROM apache/airflow:3.3.2-python3.12

USER root
# dbt ставим в отдельное виртуальное окружение, чтобы его зависимости не конфликтовали с Airflow
RUN python -m venv /opt/dbt-venv \
 && /opt/dbt-venv/bin/pip install --no-cache-dir "dbt-postgres~=1.11.0" \
 && chown -R airflow: /opt/dbt-venv \
 && mkdir -p /opt/airflow/auth && chown airflow: /opt/airflow/auth
USER airflow

# зависимости загрузчиков (код проекта монтируется в /opt/foodprices и подключается через PYTHONPATH)
COPY requirements-pipeline.txt /tmp/requirements-pipeline.txt
RUN pip install --no-cache-dir -r /tmp/requirements-pipeline.txt
