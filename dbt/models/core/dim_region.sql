select
    region_id,
    name        as region_name,
    short_name  as region_short,
    level       as region_level,
    sort_order
from {{ ref('regions') }}
