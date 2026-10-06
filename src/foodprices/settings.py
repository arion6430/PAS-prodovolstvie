"""Загрузка настроек: переменные окружения (.env) + config/config.yaml."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(os.environ.get("FOODPRICES_HOME", Path(__file__).resolve().parents[2]))


def _load_dotenv(path: Path) -> None:
    """Минимальный разбор .env без внешних зависимостей; уже заданные переменные не перезаписываются."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass(frozen=True)
class Settings:
    pg_dsn: str
    raw_dir: Path
    config_path: Path
    migrations_dir: Path
    log_level: str
    config: dict[str, Any]

    def source(self, name: str) -> dict[str, Any]:
        return self.config["sources"][name]


def load_settings() -> Settings:
    _load_dotenv(PROJECT_ROOT / ".env")
    env = os.environ
    config_path = _resolve(env.get("FOODPRICES_CONFIG", "config/config.yaml"))
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    dsn = (f"host={env.get('WAREHOUSE_HOST', 'localhost')} port={env.get('WAREHOUSE_PORT', '5432')} "
           f"dbname={env.get('WAREHOUSE_DB', 'foodprices')} user={env.get('WAREHOUSE_USER', 'foodprices')} "
           f"password={env.get('WAREHOUSE_PASSWORD', '')}")
    return Settings(
        pg_dsn=dsn,
        raw_dir=_resolve(env.get("FOODPRICES_RAW_DIR", "data/raw")),
        config_path=config_path,
        migrations_dir=PROJECT_ROOT / "sql" / "migrations",
        log_level=env.get("FOODPRICES_LOG_LEVEL", "INFO"),
        config=config,
    )


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
