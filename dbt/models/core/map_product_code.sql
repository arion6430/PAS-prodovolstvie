-- Соответствие кодов товаров в источниках единому справочнику (разрешение сущностей).
-- Один товар может иметь несколько кодов: например, «Огурцы» в ОКПД2 — 01.13.32 до 2024 г. и 01.13.32.000 после.
select
    source,
    source_code,
    source_name,
    product_id,
    to_rub_per_kg,
    coalesce(valid_from, date '1900-01-01') as valid_from,
    coalesce(valid_to,   date '9999-12-31') as valid_to,
    note
from {{ ref('product_mapping') }}
