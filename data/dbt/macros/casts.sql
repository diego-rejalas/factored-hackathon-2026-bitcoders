{#
  Casts for bronze text columns, in one place. Some integer columns arrive as
  "26.0" in the CSVs (every such value ends in .0), which a direct ::int cast
  rejects. Precision is explicit so the result does not depend on engine defaults
  (exchange rates carry 8 decimals).
#}
{% macro to_int(column) -%}
    nullif({{ column }}, '')::decimal(18,2)::integer
{%- endmacro %}

{% macro to_decimal(column) -%}
    nullif({{ column }}, '')::decimal(18,8)
{%- endmacro %}
