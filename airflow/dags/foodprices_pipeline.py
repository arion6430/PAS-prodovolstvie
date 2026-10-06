"""Конвейер данных цен на плодоовощную продукцию.

Ежедневно в 06:00 МСК: миграции схемы → параллельная инкрементальная загрузка всех источников в слой raw.
Каждый источник — отдельная задача со своими повторами: сбой одного не мешает остальным.
Подробности каждой загрузки — в таблице meta.load_log.
"""
from __future__ import annotations

import pendulum
from airflow.sdk import dag, task

SOURCES = ["emiss_retail", "emiss_producer", "cbr_fx", "cbr_key_rate", "openmeteo"]


@dag(
    dag_id="foodprices_pipeline",
    schedule="0 6 * * *",
    start_date=pendulum.datetime(2026, 10, 1, tz="Europe/Moscow"),
    catchup=False,
    max_active_runs=1,                         # загрузки не должны пересекаться
    default_args={"retries": 2, "retry_delay": pendulum.duration(minutes=5)},
    tags=["foodprices"],
    doc_md=__doc__,
)
def foodprices_pipeline():

    @task
    def migrate() -> list[str]:
        """Применяет новые миграции схемы raw/meta (идемпотентно)."""
        from foodprices.db import connect, migrate as run_migrations
        from foodprices.settings import load_settings
        s = load_settings()
        with connect(s.pg_dsn) as conn:
            return run_migrations(conn, s.migrations_dir)

    @task(map_index_template="{{ task.op_kwargs['source'] }}")
    def ingest(source: str, **context) -> dict:
        """Инкрементальная загрузка одного источника в raw."""
        from foodprices.ingest import ingest_source
        from foodprices.settings import load_settings, setup_logging
        s = load_settings()
        setup_logging(s.log_level)
        return ingest_source(s, source, run_id=context["run_id"])

    migrate() >> ingest.expand(source=SOURCES)


foodprices_pipeline()
