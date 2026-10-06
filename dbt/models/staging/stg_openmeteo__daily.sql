select
    point_id,
    obs_date::date                              as obs_date,
    {{ to_numeric('temperature_2m_mean') }}     as temp_mean_c,
    {{ to_numeric('precipitation_sum') }}       as precip_mm,
    _load_id                                    as load_id,
    _content_hash                               as content_hash
from {{ source('raw', 'openmeteo_daily') }}
