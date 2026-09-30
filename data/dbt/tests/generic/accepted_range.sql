{% test accepted_range(model, column_name, min_value=none, max_value=none) %}
{#- Returns the rows outside [min_value, max_value]; NULLs are not judged (use not_null for that). -#}
select {{ column_name }} as value
from {{ model }}
where {{ column_name }} is not null
  and (
    {% if min_value is not none %}{{ column_name }} < {{ min_value }}{% else %}false{% endif %}
    or
    {% if max_value is not none %}{{ column_name }} > {{ max_value }}{% else %}false{% endif %}
  )
{% endtest %}
