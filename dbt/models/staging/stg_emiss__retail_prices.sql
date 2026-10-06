-- Средние потребительские цены: типизация и отбор месячных наблюдений.
-- Значение, которое не удалось привести к числу, остаётся с price = null и value_raw — его ловит тест.
with src as (
    select * from {{ source('raw', 'emiss_retail_prices') }}
)
select
    okato_code,
    okato_name,
    good_code,
    good_name,
    make_date(year, {{ month_number('period_name') }}, 1)  as period_month,
    {{ to_numeric('value') }}                              as price,
    value                                                  as value_raw,
    unit,
    _load_id                                               as load_id,
    _content_hash                                          as content_hash,
    _loaded_at                                             as loaded_at
from src
where {{ month_number('period_name') }} is not null       -- накопленных периодов в 31448 нет, но фильтр общий
