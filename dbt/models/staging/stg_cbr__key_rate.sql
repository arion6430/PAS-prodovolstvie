select
    to_date(rate_date, 'DD.MM.YYYY')  as rate_date,
    {{ to_numeric('rate') }}          as key_rate_pct,
    _load_id                          as load_id,
    _content_hash                     as content_hash
from {{ source('raw', 'cbr_key_rate') }}
