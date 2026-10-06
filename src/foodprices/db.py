"""Работа с хранилищем PostgreSQL: подключение, миграции схемы, идемпотентный upsert в raw."""
from __future__ import annotations

import hashlib
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pandas as pd
import psycopg
from psycopg import sql

log = logging.getLogger(__name__)


@contextmanager
def connect(dsn: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(dsn, autocommit=False, application_name="foodprices") as conn:
        yield conn


# ---------- миграции: управление изменением схемы ----------

def migrate(conn: psycopg.Connection, migrations_dir: Path) -> list[str]:
    """Применяет по порядку ещё не применённые файлы V###__*.sql. Изменённый после применения файл — ошибка."""
    conn.execute("""
        CREATE SCHEMA IF NOT EXISTS meta;
        CREATE TABLE IF NOT EXISTS meta.schema_migrations (
            version     TEXT PRIMARY KEY,
            checksum    TEXT NOT NULL,
            applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )""")
    applied = dict(conn.execute("SELECT version, checksum FROM meta.schema_migrations").fetchall())
    done = []
    for path in sorted(migrations_dir.glob("V*__*.sql")):
        version = path.stem
        text = path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(text.encode()).hexdigest()
        if version in applied:
            if applied[version] != checksum:
                raise RuntimeError(f"Миграция {version} изменена после применения — создайте новую миграцию")
            continue
        log.info("Применяю миграцию %s", version)
        conn.execute(text)
        conn.execute("INSERT INTO meta.schema_migrations (version, checksum) VALUES (%s, %s)", (version, checksum))
        done.append(version)
    conn.commit()
    return done


# ---------- upsert в raw ----------

def upsert_raw(conn: psycopg.Connection, table: str, df: pd.DataFrame, key_cols: list[str],
               load_id: int, content_hash: str) -> dict[str, int]:
    """Идемпотентная запись в raw-таблицу.

    Новый ключ — вставка; изменилось значение — обновление (ревизия источника, её фиксирует snapshot dbt);
    совпадает — ничего не делаем. Повторный запуск с теми же данными ничего не меняет.
    """
    if df.empty:
        return {"inserted": 0, "updated": 0, "unchanged": 0}
    df = df.drop_duplicates(subset=key_cols, keep="last")
    cols = list(df.columns)
    value_cols = [c for c in cols if c not in key_cols]
    schema, name = table.split(".")
    tmp = sql.Identifier(f"tmp_{name}")

    conn.execute(sql.SQL("DROP TABLE IF EXISTS {tmp}").format(tmp=tmp))
    conn.execute(sql.SQL("CREATE TEMP TABLE {tmp} (LIKE {tbl} INCLUDING DEFAULTS) ON COMMIT DROP").format(
        tmp=tmp, tbl=sql.Identifier(schema, name)))
    with conn.cursor().copy(sql.SQL("COPY {tmp} ({cols}) FROM STDIN").format(
            tmp=tmp, cols=sql.SQL(", ").join(map(sql.Identifier, cols)))) as copy:
        for row in df.itertuples(index=False, name=None):
            copy.write_row([None if pd.isna(v) else str(v) for v in row])

    ident = lambda c: sql.Identifier(c)  # noqa: E731
    query = sql.SQL("""
        INSERT INTO {tbl} ({cols}, _first_load_id, _load_id, _content_hash)
        SELECT {cols}, %(load_id)s, %(load_id)s, %(hash)s FROM {tmp}
        ON CONFLICT ({keys}) DO UPDATE SET
            {set_values}, _load_id = EXCLUDED._load_id, _loaded_at = now(), _content_hash = EXCLUDED._content_hash
        WHERE ({target_vals}) IS DISTINCT FROM ({excluded_vals})
        RETURNING (xmax = 0) AS inserted
    """).format(
        tbl=sql.Identifier(schema, name), tmp=tmp,
        cols=sql.SQL(", ").join(map(ident, cols)),
        keys=sql.SQL(", ").join(map(ident, key_cols)),
        set_values=sql.SQL(", ").join(sql.SQL("{c} = EXCLUDED.{c}").format(c=ident(c)) for c in value_cols),
        target_vals=sql.SQL(", ").join(sql.SQL("{t}.{c}").format(t=sql.Identifier(name), c=ident(c))
                                       for c in value_cols),
        excluded_vals=sql.SQL(", ").join(sql.SQL("EXCLUDED.{c}").format(c=ident(c)) for c in value_cols),
    )
    flags = [r[0] for r in conn.execute(query, {"load_id": load_id, "hash": content_hash}).fetchall()]
    inserted = sum(flags)
    updated = len(flags) - inserted
    return {"inserted": inserted, "updated": updated, "unchanged": len(df) - len(flags)}
