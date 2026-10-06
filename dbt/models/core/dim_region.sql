select
    region_id,
    name        as region_name,
    level       as region_level,
    sort_order
from {{ ref('regions') }}
