{#
  The dataset spells Mexico two ways: 'México' (customers, branches,
  campaign_sends) and 'Mexico' (service_agents, marketing_campaigns, and both
  spellings inside digital_events.ip_country). Silver conforms it to 'México'
  so joins and accepted_values tests see one value per country.
#}
{% macro normalize_country(column) -%}
    case when {{ column }} = 'Mexico' then 'México' else {{ column }} end
{%- endmacro %}
