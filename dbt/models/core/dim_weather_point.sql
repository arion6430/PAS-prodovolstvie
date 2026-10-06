select point_id, name as point_name, lat, lon, region_id
from {{ ref('weather_points') }}
