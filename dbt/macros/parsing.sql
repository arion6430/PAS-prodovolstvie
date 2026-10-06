{# Номер месяца по русскому названию периода ЕМИСС; накопленные периоды («январь-март») дают null. #}
{% macro month_number(col) -%}
    case lower(trim({{ col }}))
        when 'январь' then 1  when 'февраль' then 2  when 'март' then 3     when 'апрель' then 4
        when 'май' then 5     when 'июнь' then 6     when 'июль' then 7     when 'август' then 8
        when 'сентябрь' then 9 when 'октябрь' then 10 when 'ноябрь' then 11 when 'декабрь' then 12
    end
{%- endmacro %}

{# Безопасное приведение текста к числу: «25,79», «1 234,5» → numeric; мусор → null (его ловят тесты). #}
{% macro to_numeric(col) -%}
    case
        when replace(replace(trim({{ col }}), ' ', ''), ',', '.') ~ '^-?[0-9]+(\.[0-9]+)?$'
        then replace(replace(trim({{ col }}), ' ', ''), ',', '.')::numeric
    end
{%- endmacro %}
