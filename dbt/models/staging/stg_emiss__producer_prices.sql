-- Средние цены производителей: только месячные периоды (накопленные «январь-март» и т.п. отбрасываются)
-- и только цены за тонну (ОКЕИ 168) — другие единицы относятся к яйцам и т.п.
-- Значение «0» Росстат публикует там, где данных нет или они скрыты (конфиденциальность), — это не цена:
-- price = null, флаг is_zero_placeholder для контроля качества.
with src as (
    select * from {{ source('raw', 'emiss_producer_prices') }}
)
select
    okato_code,
    okato_name,
    okpd2_code,
    okpd2_name,
    okei_code,
    make_date(year, {{ month_number('period_name') }}, 1)  as period_month,
    nullif({{ to_numeric('value') }}, 0)                   as price,
    {{ to_numeric('value') }} = 0                          as is_zero_placeholder,
    value                                                  as value_raw,
    _load_id                                               as load_id,
    _content_hash                                          as content_hash,
    _loaded_at                                             as loaded_at
from src
where {{ month_number('period_name') }} is not null
  and okei_code = '168'
