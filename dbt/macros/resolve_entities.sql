{#
  Разрешение сущностей для фактов ЕМИСС: коды товара и региона источника → единые product_id / region_id.
  Если на одну пару «товар × регион × месяц» приходится несколько строк источника (старый и новый код,
  разные редакции округа), остаётся одна: сначала строка, у которой месяц попадает в период действия обоих
  кодов, затем — с более поздним кодом. Число кандидатов сохраняется для контроля качества.
#}
{% macro resolve_entities(staging_model, source_name, product_code_col) %}
with s as (
    select * from {{ ref(staging_model) }}
    where price is not null
),
mapped as (
    select
        s.*,
        p.product_id,
        p.to_rub_per_kg,
        r.region_id,
        (s.period_month between p.valid_from and p.valid_to
         and s.period_month between r.valid_from and r.valid_to)  as code_in_validity,
        greatest(p.valid_from, r.valid_from)                       as code_valid_from
    from s
    join {{ ref('map_product_code') }} p
      on p.source = '{{ source_name }}' and p.source_code = s.{{ product_code_col }}
    join {{ ref('map_region_code') }} r
      on r.source_code = s.okato_code
),
ranked as (
    select
        *,
        row_number() over w as rn,
        count(*)     over (partition by product_id, region_id, period_month) as n_candidates
    from mapped
    window w as (partition by product_id, region_id, period_month
                 order by code_in_validity desc, code_valid_from desc, okato_code)
)
select
    product_id,
    region_id,
    period_month,
    round(price * to_rub_per_kg, 2)  as price_rub_kg,
    okato_code                       as source_region_code,
    {{ product_code_col }}           as source_product_code,
    code_in_validity,
    n_candidates,
    load_id,
    content_hash
from ranked
where rn = 1
{% endmacro %}
