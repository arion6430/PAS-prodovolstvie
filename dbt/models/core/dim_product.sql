select
    product_id,
    name          as product_name,
    category,
    origin,
    origin in ('импортный', 'смешанный') as is_import_dependent,
    description
from {{ ref('products') }}
