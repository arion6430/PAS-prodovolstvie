"""Конвейер данных цен на плодоовощную продукцию.

Ежедневно в 06:00 МСК:
1. миграции схемы raw/meta;
2. параллельная инкрементальная загрузка всех источников в слой raw (журнал — meta.load_log);
3. dbt build: справочники (seeds) → снимки истории (snapshots) → staging → core → marts, с тестами качества
   после каждой модели. Ошибка теста с severity=error останавливает зависящие модели.

dbt запускается, даже если какой-то источник не загрузился (trigger_rule=all_done): витрины
пересобираются на последних доступных данных, а сбой виден в журнале загрузок и на операционном дашборде.
"""
from __future__ import annotations

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag, task

SOURCES = ["emiss_retail", "emiss_producer", "cbr_fx", "cbr_key_rate", "openmeteo"]
DBT = "cd /opt/foodprices/dbt && /opt/dbt-venv/bin/dbt"


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

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"{DBT} build",
        trigger_rule="all_done",
        retries=0,                             # падение dbt — это проблема данных или кода, повтор не поможет
    )

    migrate() >> ingest.expand(source=SOURCES) >> dbt_build


foodprices_pipeline()
