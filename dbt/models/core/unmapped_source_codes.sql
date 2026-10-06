-- Ссылочная целостность: коды из источников, которых нет в мастер-справочниках.
-- Такие строки не попадают в факты; появление новых кодов — сигнал обновить справочник.
with retail as (
    select distinct 'emiss_retail' as source, 'product' as entity, good_code as source_code, good_name as source_name
    from {{ ref('stg_emiss__retail_prices') }}
    union all
    select distinct 'emiss_retail', 'region', okato_code, okato_name
    from {{ ref('stg_emiss__retail_prices') }}
),
producer as (
    select distinct 'emiss_producer' as source, 'product' as entity, okpd2_code, okpd2_name
    from {{ ref('stg_emiss__producer_prices') }}
    union all
    select distinct 'emiss_producer', 'region', okato_code, okato_name
    from {{ ref('stg_emiss__producer_prices') }}
),
all_codes as (
    select * from retail
    union all
    select * from producer
)
select a.*
from all_codes a
left join {{ ref('map_product_code') }} p
  on a.entity = 'product' and p.source = a.source and p.source_code = a.source_code
left join {{ ref('map_region_code') }} r
  on a.entity = 'region' and r.source_code = a.source_code
where p.source_code is null and r.source_code is null
