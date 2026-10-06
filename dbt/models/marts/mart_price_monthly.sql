-- Основная предметная витрина: цена товара в регионе по месяцам с производными показателями.
-- Отвечает на вопросы: «как менялась цена», «насколько она выше сезонной нормы», «какова наценка к цене
-- производителя», «на фоне какого курса и ставки». Сравнения делаются по датам (а не по соседним строкам),
-- поэтому пропуски месяцев в рядах не искажают показатели.
with retail as (
    select product_id, region_id, period_month, price_rub_kg, source_region_code, source_product_code
    from {{ ref('fct_retail_price_monthly') }}
),
norm as (
    -- сезонная норма: средняя цена того же календарного месяца за 5 предыдущих лет (не меньше 3 наблюдений)
    select r.product_id, r.region_id, r.period_month,
           avg(h.price_rub_kg) as seasonal_norm, count(h.price_rub_kg) as norm_years
    from retail r
    join retail h
      on h.product_id = r.product_id and h.region_id = r.region_id
     and h.period_month in (r.period_month - interval '1 year', r.period_month - interval '2 year',
                            r.period_month - interval '3 year', r.period_month - interval '4 year',
                            r.period_month - interval '5 year')
    group by 1, 2, 3
    having count(h.price_rub_kg) >= 3
),
fx as (
    select date_trunc('month', rate_date)::date as period_month, avg(rub_per_unit) as usd_rub
    from {{ ref('fct_fx_daily') }} where currency = 'USD' group by 1
),
kr as (
    select date_trunc('month', rate_date)::date as period_month, avg(key_rate_pct) as key_rate_pct
    from {{ ref('fct_key_rate_daily') }} group by 1
)
select
    c.product_id,
    p.product_name,
    p.category,
    p.origin,
    c.region_id,
    g.region_name,
    g.region_level,
    g.sort_order                                                            as region_sort,
    c.period_month,
    c.price_rub_kg,
    pm.price_rub_kg                                                         as price_prev_month,
    round(100 * (c.price_rub_kg / nullif(pm.price_rub_kg, 0) - 1), 1)       as mom_pct,
    py.price_rub_kg                                                         as price_prev_year,
    round(100 * (c.price_rub_kg / nullif(py.price_rub_kg, 0) - 1), 1)       as yoy_pct,
    round(n.seasonal_norm, 2)                                               as seasonal_norm_rub_kg,
    round(100 * (c.price_rub_kg / nullif(n.seasonal_norm, 0) - 1), 1)       as dev_from_norm_pct,
    pp.price_rub_kg                                                         as producer_price_rub_kg,
    round(c.price_rub_kg / nullif(pp.price_rub_kg, 0), 2)                   as retail_to_producer_ratio,
    round(fx.usd_rub, 2)                                                    as usd_rub,
    round(kr.key_rate_pct, 2)                                               as key_rate_pct,
    c.source_region_code,
    c.source_product_code
from retail c
join {{ ref('dim_product') }} p using (product_id)
join {{ ref('dim_region') }}  g using (region_id)
left join retail pm
       on pm.product_id = c.product_id and pm.region_id = c.region_id
      and pm.period_month = c.period_month - interval '1 month'
left join retail py
       on py.product_id = c.product_id and py.region_id = c.region_id
      and py.period_month = c.period_month - interval '1 year'
left join norm n
       on n.product_id = c.product_id and n.region_id = c.region_id and n.period_month = c.period_month
left join {{ ref('fct_producer_price_monthly') }} pp
       on pp.product_id = c.product_id and pp.region_id = c.region_id and pp.period_month = c.period_month
left join fx on fx.period_month = c.period_month
left join kr on kr.period_month = c.period_month
