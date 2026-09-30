{#
  Casts for bronze text columns. In DuckDB a bare `::numeric` is DECIMAL(18,3),
  which silently rounds values that need more decimals (exchange rates carry 8),
  so precision is always explicit. Some integer columns arrive as "26.0" in the
  CSVs (every such value ends in .0), which a direct ::int cast rejects.
#}
{% macro to_int(column) -%}
    nullif({{ column }}, '')::decimal(18,2)::integer
{%- endmacro %}

{% macro to_decimal(column) -%}
    nullif({{ column }}, '')::decimal(18,8)
{%- endmacro %}
