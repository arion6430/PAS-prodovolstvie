select w.point_id, p.region_id, w.obs_date, w.temp_mean_c, w.precip_mm, w.load_id, w.content_hash
from {{ ref('stg_openmeteo__daily') }} w
join {{ ref('dim_weather_point') }} p using (point_id)
