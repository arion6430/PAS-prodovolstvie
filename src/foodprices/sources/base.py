"""Общий интерфейс загрузчика источника."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from typing import Any, Iterable

import pandas as pd
import psycopg

from ..http import HttpClient
from ..settings import PROJECT_ROOT

SEEDS = PROJECT_ROOT / "dbt" / "seeds"   # мастер-справочники общие для загрузчиков и dbt


class SchemaChanged(RuntimeError):
    """Структура ответа источника не совпадает с ожидаемой — загрузку нужно остановить и разобраться."""


@dataclass
class Request:
    """Один запрос к источнику в рамках инкрементального окна."""
    params: dict[str, Any]


@dataclass
class Payload:
    content: bytes            # ответ как есть — уходит в сырой файл
    fingerprint: bytes        # содержимое без изменчивых частей — по нему считаем хеш
    ext: str
    warnings: list[str] = field(default_factory=list)


class Source:
    name: str
    table: str                # raw-таблица
    key_cols: list[str]

    def __init__(self, cfg: dict[str, Any], http: HttpClient):
        self.cfg = cfg
        self.http = http

    def plan(self, conn: psycopg.Connection) -> Iterable[Request]:
        """Список запросов: только то, чего ещё нет в хранилище (+ перекрытие для ревизий)."""
        raise NotImplementedError

    def fetch(self, req: Request) -> Payload:
        raise NotImplementedError

    def parse(self, payload: Payload) -> pd.DataFrame:
        """Разбор ответа в строки raw-таблицы. Значения остаются текстом, как в источнике."""
        raise NotImplementedError


def require_columns(df: pd.DataFrame, expected: Iterable[str], source: str) -> None:
    missing = set(expected) - set(df.columns)
    if missing:
        raise SchemaChanged(f"{source}: в ответе нет полей {sorted(missing)}; есть {sorted(df.columns)}")


def read_seed(name: str) -> list[dict[str, str]]:
    with open(SEEDS / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))
