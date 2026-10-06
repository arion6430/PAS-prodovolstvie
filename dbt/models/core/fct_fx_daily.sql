select currency, rate_date, rub_per_unit, load_id, content_hash
from {{ ref('stg_cbr__fx_rates') }}
where rub_per_unit is not null
