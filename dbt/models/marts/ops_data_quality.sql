-- Операционная витрина: сводные показатели качества данных после обработки.
-- Каждая строка — один контроль: сколько записей затронуто и что система с ними делает.
select 'Коды источников без соответствия в справочниках' as check_name,
       'ссылочная целостность' as check_type,
       count(*) as affected_rows,
       'строки не попадают в факты; нужно дополнить справочник' as system_action
from {{ ref('unmapped_source_codes') }}

union all
select 'Нули-заглушки Росстата в ценах производителей', 'допустимость значений',
       count(*) filter (where is_zero_placeholder),
       'значение заменено на пустое, в расчётах не участвует'
from {{ ref('stg_emiss__producer_prices') }}

union all
select 'Нераспознанные числа в исходных данных', 'соответствие типов',
       (select count(*) from {{ ref('stg_emiss__retail_prices') }} where value_raw is not null and price is null)
     + (select count(*) from {{ ref('stg_emiss__producer_prices') }}
        where value_raw is not null and price is null and not coalesce(is_zero_placeholder, false)),
       'строка отбрасывается из фактов, тест dbt падает'

union all
select 'Дубли, устранённые при склейке рядов (старый/новый код)', 'уникальность',
       coalesce(sum(n_candidates - 1), 0),
       'оставлена версия по действующему коду'
from (
    select n_candidates from {{ ref('fct_retail_price_monthly') }}
    union all
    select n_candidates from {{ ref('fct_producer_price_monthly') }}
) t

union all
select 'Значения взяты по коду вне периода его действия', 'актуальность справочника',
       count(*),
       'значение используется, т.к. другого нет; предупреждение dbt'
from (
    select code_in_validity from {{ ref('fct_retail_price_monthly') }}
    union all
    select code_in_validity from {{ ref('fct_producer_price_monthly') }}
) t
where not code_in_validity

union all
select 'Ревизии опубликованных значений Росстатом', 'историзация',
       (select count(*) from {{ ref('snp_emiss_retail_prices') }} where dbt_valid_to is not null)
     + (select count(*) from {{ ref('snp_emiss_producer_prices') }} where dbt_valid_to is not null),
       'старая версия сохранена в снимке, в витринах — актуальная'
