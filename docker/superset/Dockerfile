FROM apache/superset:6.1.0

# драйвер PostgreSQL: и для метаданных Superset, и для подключения к хранилищу
USER root
RUN uv pip install --python /app/.venv/bin/python --no-cache "psycopg2-binary>=2.9"
USER superset

COPY superset_config.py /app/pythonpath/superset_config.py
