"""Журнал загрузок и хранение сырых ответов источников."""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg

log = logging.getLogger(__name__)


@dataclass
class LoadStats:
    requests_total: int = 0
    requests_failed: int = 0
    rows_received: int = 0
    rows_inserted: int = 0
    rows_updated: int = 0
    rows_unchanged: int = 0
    warnings: list[str] = field(default_factory=list)

    def add(self, counts: dict[str, int]) -> None:
        self.rows_inserted += counts["inserted"]
        self.rows_updated += counts["updated"]
        self.rows_unchanged += counts["unchanged"]


def start_load(conn: psycopg.Connection, source: str, run_id: str | None, params: dict) -> int:
    # загрузки, оставшиеся в статусе running после аварийного завершения процесса, закрываем как failed
    stale = conn.execute(
        "UPDATE meta.load_log SET status = 'failed', finished_at = now(), "
        "error = 'Прервано: процесс загрузки завершился аварийно' "
        "WHERE source = %s AND status = 'running' RETURNING load_id", (source,)).fetchall()
    if stale:
        log.warning("[%s] найдены прерванные загрузки %s — отмечены как failed", source, [r[0] for r in stale])
    load_id = conn.execute(
        "INSERT INTO meta.load_log (run_id, source, status, params) VALUES (%s, %s, 'running', %s) "
        "RETURNING load_id", (run_id, source, json.dumps(params, ensure_ascii=False, default=str))).fetchone()[0]
    conn.commit()
    return load_id


def finish_load(conn: psycopg.Connection, load_id: int, status: str, stats: LoadStats,
                error: str | None = None) -> None:
    conn.execute(
        """UPDATE meta.load_log SET status = %s, finished_at = now(), requests_total = %s, requests_failed = %s,
               rows_received = %s, rows_inserted = %s, rows_updated = %s, rows_unchanged = %s,
               warnings = %s, error = %s
           WHERE load_id = %s""",
        (status, stats.requests_total, stats.requests_failed, stats.rows_received, stats.rows_inserted,
         stats.rows_updated, stats.rows_unchanged, json.dumps(stats.warnings, ensure_ascii=False), error, load_id))
    conn.commit()


def store_raw(conn: psycopg.Connection, raw_dir: Path, source: str, load_id: int, content: bytes,
              fingerprint: bytes, ext: str, request: dict[str, Any]) -> tuple[str, bool]:
    """Сохраняет сырой ответ в gzip-файл с именем по хешу и регистрирует его.

    fingerprint — содержимое без изменчивых частей (например, время формирования в заголовке SDMX),
    поэтому одинаковые данные дают одинаковый хеш. Возвращает (хеш, файл_новый).
    """
    content_hash = hashlib.sha256(fingerprint).hexdigest()
    rel = Path(source) / content_hash[:2] / f"{content_hash}.{ext}.gz"
    known = conn.execute("SELECT 1 FROM meta.raw_files WHERE content_hash = %s", (content_hash,)).fetchone()
    is_new = known is None
    if is_new:
        path = raw_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wb") as f:
            f.write(content)
        conn.execute("INSERT INTO meta.raw_files (content_hash, source, path, bytes, first_load_id) "
                     "VALUES (%s, %s, %s, %s, %s)", (content_hash, source, rel.as_posix(), len(content), load_id))
    conn.execute("INSERT INTO meta.load_files (load_id, content_hash, request, is_new) VALUES (%s, %s, %s, %s) "
                 "ON CONFLICT DO NOTHING",
                 (load_id, content_hash, json.dumps(request, ensure_ascii=False, default=str), is_new))
    return content_hash, is_new
