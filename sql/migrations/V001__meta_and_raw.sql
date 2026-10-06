-- V001: служебная схема meta (журнал загрузок) и слой raw (данные источников «как есть»).
-- Слой raw заполняется только загрузчиками на Python; всё, что дальше (staging/core/marts), строит dbt.

CREATE SCHEMA IF NOT EXISTS meta;
CREATE SCHEMA IF NOT EXISTS raw;

-- Журнал загрузок: одна строка = один запуск загрузчика одного источника.
CREATE TABLE IF NOT EXISTS meta.load_log (
    load_id          BIGSERIAL PRIMARY KEY,
    run_id           TEXT,                       -- идентификатор запуска оркестратора (Airflow run_id) или CLI
    source           TEXT        NOT NULL,
    status           TEXT        NOT NULL CHECK (status IN ('running', 'success', 'unchanged', 'partial', 'failed')),
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at      TIMESTAMPTZ,
    params           JSONB,                      -- окно инкрементальной загрузки и прочие параметры запроса
    requests_total   INT         DEFAULT 0,
    requests_failed  INT         DEFAULT 0,
    rows_received    INT         DEFAULT 0,      -- строк в ответах источника
    rows_inserted    INT         DEFAULT 0,      -- новых ключей
    rows_updated     INT         DEFAULT 0,      -- изменилось значение по существующему ключу (ревизия)
    rows_unchanged   INT         DEFAULT 0,
    warnings         JSONB       DEFAULT '[]'::jsonb,
    error            TEXT
);
CREATE INDEX IF NOT EXISTS load_log_source_idx ON meta.load_log (source, started_at DESC);

-- Сырые ответы источников, сохранённые на диск (контент-адресное хранение: имя файла = хеш содержимого).
CREATE TABLE IF NOT EXISTS meta.raw_files (
    content_hash     TEXT PRIMARY KEY,
    source           TEXT        NOT NULL,
    path             TEXT        NOT NULL,
    bytes            BIGINT      NOT NULL,
    first_load_id    BIGINT      REFERENCES meta.load_log (load_id),
    first_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Какие файлы получены в каком запуске (один и тот же файл может прийти многократно).
CREATE TABLE IF NOT EXISTS meta.load_files (
    load_id          BIGINT NOT NULL REFERENCES meta.load_log (load_id),
    content_hash     TEXT   NOT NULL REFERENCES meta.raw_files (content_hash),
    request          JSONB,
    is_new           BOOLEAN NOT NULL,
    PRIMARY KEY (load_id, content_hash)
);

-- Общие служебные колонки raw-таблиц:
--   _first_load_id / _first_seen_at — когда ключ появился впервые;
--   _load_id / _loaded_at           — последняя загрузка, изменившая значение;
--   _content_hash                   — из какого сырого файла пришло текущее значение (lineage до файла).

-- ЕМИСС 31448: средние потребительские цены. Значения хранятся как текст, как в источнике («25,79»).
CREATE TABLE IF NOT EXISTS raw.emiss_retail_prices (
    okato_code     TEXT NOT NULL,
    okato_name     TEXT,
    good_code      TEXT NOT NULL,
    good_name      TEXT,
    unit           TEXT,
    year           INT  NOT NULL,
    period_name    TEXT NOT NULL,
    value          TEXT,
    _first_load_id BIGINT, _first_seen_at TIMESTAMPTZ DEFAULT now(),
    _load_id       BIGINT, _loaded_at     TIMESTAMPTZ DEFAULT now(),
    _content_hash  TEXT,
    PRIMARY KEY (okato_code, good_code, year, period_name)
);

-- ЕМИСС 57693: средние цены производителей с/х продукции (ОКПД2).
CREATE TABLE IF NOT EXISTS raw.emiss_producer_prices (
    okato_code     TEXT NOT NULL,
    okato_name     TEXT,
    okpd2_code     TEXT NOT NULL,
    okpd2_name     TEXT,
    okei_code      TEXT NOT NULL,
    okei_name      TEXT,
    year           INT  NOT NULL,
    period_name    TEXT NOT NULL,
    value          TEXT,
    _first_load_id BIGINT, _first_seen_at TIMESTAMPTZ DEFAULT now(),
    _load_id       BIGINT, _loaded_at     TIMESTAMPTZ DEFAULT now(),
    _content_hash  TEXT,
    PRIMARY KEY (okato_code, okpd2_code, okei_code, year, period_name)
);

-- Банк России: официальные курсы валют.
CREATE TABLE IF NOT EXISTS raw.cbr_fx_rates (
    currency_id    TEXT NOT NULL,     -- внутренний код ЦБ, напр. R01235
    char_code      TEXT,
    rate_date      TEXT NOT NULL,     -- как в источнике: ДД.ММ.ГГГГ
    nominal        TEXT,
    value          TEXT,
    _first_load_id BIGINT, _first_seen_at TIMESTAMPTZ DEFAULT now(),
    _load_id       BIGINT, _loaded_at     TIMESTAMPTZ DEFAULT now(),
    _content_hash  TEXT,
    PRIMARY KEY (currency_id, rate_date)
);

-- Банк России: ключевая ставка (HTML-таблица).
CREATE TABLE IF NOT EXISTS raw.cbr_key_rate (
    rate_date      TEXT NOT NULL,
    rate           TEXT,
    _first_load_id BIGINT, _first_seen_at TIMESTAMPTZ DEFAULT now(),
    _load_id       BIGINT, _loaded_at     TIMESTAMPTZ DEFAULT now(),
    _content_hash  TEXT,
    PRIMARY KEY (rate_date)
);

-- Open-Meteo: дневная погода в точках агрорегионов.
CREATE TABLE IF NOT EXISTS raw.openmeteo_daily (
    point_id       TEXT NOT NULL,
    obs_date       TEXT NOT NULL,
    temperature_2m_mean TEXT,
    precipitation_sum   TEXT,
    _first_load_id BIGINT, _first_seen_at TIMESTAMPTZ DEFAULT now(),
    _load_id       BIGINT, _loaded_at     TIMESTAMPTZ DEFAULT now(),
    _content_hash  TEXT,
    PRIMARY KEY (point_id, obs_date)
);
