-- Последний опубликованный месяц по каждому товару и региону: «сколько стоит сейчас и что подорожало».
select *
from (
    select m.*, row_number() over (partition by product_id, region_id order by period_month desc) as rn
    from {{ ref('mart_price_monthly') }} m
) t
where rn = 1
