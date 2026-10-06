-- Официальные курсы: рублей за одну единицу валюты (с учётом номинала, например 10 CNY).
select
    char_code                                                   as currency,
    to_date(rate_date, 'DD.MM.YYYY')                            as rate_date,
    {{ to_numeric('value') }} / nullif({{ to_numeric('nominal') }}, 0) as rub_per_unit,
    _load_id                                                    as load_id,
    _content_hash                                               as content_hash
from {{ source('raw', 'cbr_fx_rates') }}
