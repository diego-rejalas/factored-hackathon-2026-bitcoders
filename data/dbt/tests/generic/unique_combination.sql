{% test unique_combination(model, column_names) %}
{#- For composite keys such as daily_exchange_rates (rate_date, source_currency, target_currency). -#}
select {{ column_names | join(', ') }}, count(*) as n_rows
from {{ model }}
group by {{ column_names | join(', ') }}
having count(*) > 1
{% endtest %}
