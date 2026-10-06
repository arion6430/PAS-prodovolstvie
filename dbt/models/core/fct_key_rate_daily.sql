select rate_date, key_rate_pct, load_id, content_hash
from {{ ref('stg_cbr__key_rate') }}
where key_rate_pct is not null
