{# Используем имена схем как есть (staging, core, marts), без префикса схемы профиля. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name | trim if custom_schema_name is not none else target.schema }}
{%- endmacro %}
