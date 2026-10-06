-- Зависимость цены от курса доллара: корреляция годовых изменений цены и курса (Россия в целом),
-- одновременно и с лагом 3 месяца (импортные контракты пересматриваются не сразу).
-- Отвечает на вопрос «какие товары подорожают, если ослабнет рубль».
with m as (
    select product_id, product_name, origin, period_month,
           ln(price_rub_kg / nullif(price_prev_year, 0)) as price_log_yoy
    from {{ ref('mart_price_monthly') }}
    where region_id = 'RU' and price_prev_year is not null
),
usd as (
    select period_month, usd_rub from {{ ref('mart_price_monthly') }}
    where region_id = 'RU' and usd_rub is not null
    group by 1, 2
),
usd_chg as (
    select u.period_month,
           ln(u.usd_rub / y.usd_rub)  as usd_log_yoy,
           ln(l.usd_rub / ly.usd_rub) as usd_log_yoy_lag3
    from usd u
    join usd y  on y.period_month  = u.period_month - interval '1 year'
    left join usd l  on l.period_month  = u.period_month - interval '3 month'
    left join usd ly on ly.period_month = u.period_month - interval '15 month'
),
pairs as (
    select m.*, c.usd_log_yoy, c.usd_log_yoy_lag3
    from m join usd_chg c using (period_month)
)
select
    product_id,
    product_name,
    origin,
    round(corr(price_log_yoy, usd_log_yoy)::numeric, 2)       as corr_with_usd,
    round(corr(price_log_yoy, usd_log_yoy_lag3)::numeric, 2)  as corr_with_usd_lag3,
    count(*)                                                  as n_months,
    case
        when count(*) < 36 then 'мало данных'        -- корреляция по нескольким точкам ненадёжна
        when greatest(corr(price_log_yoy, usd_log_yoy), corr(price_log_yoy, usd_log_yoy_lag3)) >= 0.5 then 'сильная'
        when greatest(corr(price_log_yoy, usd_log_yoy), corr(price_log_yoy, usd_log_yoy_lag3)) >= 0.3 then 'умеренная'
        else 'слабая'
    end                                                       as dependence
from pairs
group by product_id, product_name, origin
