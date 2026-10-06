{# Собственные generic-тесты качества (без внешних пакетов). Тест падает, если запрос вернул строки. #}

{# Уникальность составного ключа. #}
{% test unique_combination(model, columns) %}
select {{ columns | join(', ') }}, count(*) as n
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1
{% endtest %}

{# Допустимый диапазон значений (границы включительно, null не проверяется). #}
{% test in_range(model, column_name, min_value=none, max_value=none) %}
select *
from {{ model }}
where {{ column_name }} is not null
  and (
      false
      {% if min_value is not none %} or {{ column_name }} < {{ min_value }} {% endif %}
      {% if max_value is not none %} or {{ column_name }} > {{ max_value }} {% endif %}
  )
{% endtest %}

{# Соответствие типов: исходный текст не удалось привести к числу. #}
{% test parsed_as_number(model, column_name, raw_column) %}
select *
from {{ model }}
where {{ raw_column }} is not null and {{ column_name }} is null
{% endtest %}

{# Модель должна быть пустой (например, список нарушений). #}
{% test is_empty(model) %}
select * from {{ model }}
{% endtest %}
