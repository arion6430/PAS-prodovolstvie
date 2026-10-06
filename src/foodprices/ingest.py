"""Загрузка источника в слой raw: план инкрементального окна → запросы → сырые файлы → upsert → журнал."""
from __future__ import annotations

import logging
from dataclasses import asdict

from .db import connect, upsert_raw
from .http import HttpClient, SourceUnavailable
from .loadlog import LoadStats, finish_load, start_load, store_raw
from .settings import Settings
from .sources import SOURCES
from .sources.base import SchemaChanged

log = logging.getLogger(__name__)


def ingest_source(settings: Settings, name: str, run_id: str | None = None) -> dict:
    """Загружает один источник. Сбой отдельного запроса не прерывает остальные запросы окна;
    итоговый статус: success / unchanged / partial / failed. Исключение пробрасывается только при failed."""
    cfg = settings.source(name)
    http_cfg = {**settings.config["http"], **cfg.get("http", {})}  # общие настройки + переопределения источника
    source = SOURCES[name](cfg, HttpClient.from_config(http_cfg))
    stats = LoadStats()
    with connect(settings.pg_dsn) as conn:
        requests_ = list(source.plan(conn))
        load_id = start_load(conn, name, run_id, {"requests": [r.params for r in requests_]})
        log.info("[%s] load_id=%s, запросов: %d", name, load_id, len(requests_))
        errors: list[str] = []
        for req in requests_:
            stats.requests_total += 1
            try:
                payload = source.fetch(req)
                stats.warnings += [w for w in payload.warnings if w not in stats.warnings]
                content_hash, is_new = store_raw(conn, settings.raw_dir, name, load_id, payload.content,
                                                 payload.fingerprint, payload.ext, req.params)
                df = source.parse(payload)
                stats.rows_received += len(df)
                counts = upsert_raw(conn, source.table, df, source.key_cols, load_id, content_hash)
                conn.commit()
                stats.add(counts)
                log.info("[%s] %s: строк %d, новых %d, изменённых %d, без изменений %d%s", name,
                         _short(req.params), len(df), counts["inserted"], counts["updated"], counts["unchanged"],
                         "" if is_new else " (такой ответ уже получали)")
            except (SourceUnavailable, SchemaChanged, ValueError, KeyError) as e:
                conn.rollback()
                stats.requests_failed += 1
                errors.append(f"{_short(req.params)}: {type(e).__name__}: {e}")
                log.error("[%s] запрос %s не выполнен: %s", name, _short(req.params), e)

        if stats.requests_total and stats.requests_failed == stats.requests_total:
            status = "failed"
        elif stats.requests_failed:
            status = "partial"
        elif stats.rows_inserted or stats.rows_updated:
            status = "success"
        else:
            status = "unchanged"
        finish_load(conn, load_id, status, stats, "\n".join(errors) or None)
    for w in stats.warnings:
        log.warning("[%s] %s", name, w)
    result = {"source": name, "load_id": load_id, "status": status, **asdict(stats)}
    if status == "failed":
        raise RuntimeError(f"Источник {name} недоступен: {errors[0] if errors else ''}")
    return result


def _short(params: dict) -> str:
    """Краткое описание запроса для лога (без длинных списков товаров)."""
    return ", ".join(f"{k}={v}" for k, v in params.items() if k not in ("products", "regions"))
