{#
  dbt's default behavior appends the custom schema to the target schema
  (e.g. "bronze_silver"). We want exact schema names ("silver", "gold") so
  the tool layer and the ingestion DAG can rely on fixed, predictable names.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
