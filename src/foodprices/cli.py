"""Командная строка: python -m foodprices <команда>."""
from __future__ import annotations

import argparse
import logging
import sys

from .db import connect, migrate
from .ingest import ingest_source
from .settings import load_settings, setup_logging
from .sources import SOURCES

log = logging.getLogger("foodprices")


def cmd_migrate(settings, args) -> int:
    with connect(settings.pg_dsn) as conn:
        done = migrate(conn, settings.migrations_dir)
    log.info("Миграции применены: %s", done or "нет новых")
    return 0


def cmd_ingest(settings, args) -> int:
    names = [n for n, c in settings.config["sources"].items() if c.get("enabled", True)] \
        if args.source == "all" else [args.source]
    failed = 0
    for name in names:
        try:
            r = ingest_source(settings, name, run_id=args.run_id)
            log.info("[%s] %s: +%d новых, ~%d изменённых, =%d без изменений", name, r["status"],
                     r["rows_inserted"], r["rows_updated"], r["rows_unchanged"])
        except Exception as e:  # noqa: BLE001 — один источник не должен останавливать остальные
            failed += 1
            log.error("[%s] загрузка не удалась: %s", name, e)
    return 1 if failed else 0


def cmd_status(settings, args) -> int:
    with connect(settings.pg_dsn) as conn:
        rows = conn.execute("""
            SELECT DISTINCT ON (source) source, load_id, status, started_at::timestamp(0),
                   rows_received, rows_inserted, rows_updated, requests_failed
            FROM meta.load_log ORDER BY source, started_at DESC""").fetchall()
    print(f"{'источник':<16}{'load_id':>8}  {'статус':<10}{'начало':<21}{'строк':>8}{'нов':>8}{'изм':>6}{'ошиб':>6}")
    for r in rows:
        print(f"{r[0]:<16}{r[1]:>8}  {r[2]:<10}{str(r[3]):<21}{r[4]:>8}{r[5]:>8}{r[6]:>6}{r[7]:>6}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="foodprices", description="Конвейер данных цен на плодоовощную продукцию")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="применить миграции схемы хранилища")
    p = sub.add_parser("ingest", help="загрузить источник(и) в слой raw")
    p.add_argument("--source", default="all", choices=["all", *SOURCES])
    p.add_argument("--run-id", default=None, help="идентификатор запуска (для журнала)")
    sub.add_parser("status", help="последняя загрузка по каждому источнику")
    args = parser.parse_args(argv)

    settings = load_settings()
    setup_logging(settings.log_level)
    return {"migrate": cmd_migrate, "ingest": cmd_ingest, "status": cmd_status}[args.cmd](settings, args)


if __name__ == "__main__":
    sys.exit(main())
