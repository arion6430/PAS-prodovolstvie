-- Соответствие кодов ОКАТО единому справочнику регионов с периодами действия.
-- Пример: Россия до 2023 г. — код 643, с 2023 г. — 643004.АГ (без учёта новых субъектов).
select
    source_code,
    source_name,
    region_id,
    coalesce(valid_from, date '1900-01-01') as valid_from,
    coalesce(valid_to,   date '9999-12-31') as valid_to,
    note
from {{ ref('region_mapping') }}
