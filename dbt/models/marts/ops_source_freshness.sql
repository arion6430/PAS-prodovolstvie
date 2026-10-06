-- Операционная витрина: свежи ли данные каждого источника и когда он последний раз успешно загружался.
-- Для месячных данных отставание считается от конца последнего опубликованного месяца.
with last_data as (
    select 'emiss_retail' as source, (max(period_month) + interval '1 month' - interval '1 day')::date as last_data_date
    from {{ ref('fct_retail_price_monthly') }}
    union all
    select 'emiss_producer', (max(period_month) + interval '1 month' - interval '1 day')::date
    from {{ ref('fct_producer_price_monthly') }}
    union all
    select 'cbr_fx', max(rate_date) from {{ ref('fct_fx_daily') }}
    union all
    select 'cbr_key_rate', max(rate_date) from {{ ref('fct_key_rate_daily') }}
    union all
    select 'openmeteo', max(obs_date) from {{ ref('fct_weather_daily') }}
),
loads as (
    select
        source,
        max(started_at)                                                        as last_run_at,
        max(started_at) filter (where status in ('success', 'unchanged'))      as last_ok_run_at,
        (array_agg(status order by started_at desc))[1]                        as last_status,
        count(*) filter (where status in ('failed', 'partial')
                         and started_at > now() - interval '7 day')            as problems_7d
    from {{ source('meta', 'load_log') }}
    where status <> 'running'
    group by source
)
select
    s.source,
    s.source_title,
    s.frequency,
    d.last_data_date,
    current_date - d.last_data_date                                 as lag_days,
    s.max_lag_days,
    (l.last_run_at    at time zone 'Europe/Moscow')::timestamp(0)   as last_run_msk,
    (l.last_ok_run_at at time zone 'Europe/Moscow')::timestamp(0)   as last_ok_run_msk,
    l.last_status,
    coalesce(l.problems_7d, 0)                                      as problems_7d,
    case
        when d.last_data_date is null                       then 'нет данных'
        when current_date - d.last_data_date > s.max_lag_days then 'устарели'
        when l.last_status in ('failed', 'partial')         then 'сбой загрузки'
        else 'в норме'
    end                                                             as freshness_status
from {{ ref('source_sla') }} s
left join last_data d using (source)
left join loads l using (source)
