-- description/resolution are templated text, not real free text — see
-- spec/DATA_FINDINGS.md. category/subcategory are the real structured
-- signal; don't build NLP intent classification on the text fields here.
with source as (
    select * from {{ source('bronze', 'complaints') }}
)

select
    complaint_id,
    creation_date::timestamp                              as creation_date,
    process_date::date                                    as process_date,
    customer_id,
    case_type,
    category,
    nullif(subcategory, '')                                as subcategory,
    reception_channel,
    nullif(affected_product_id, '')                        as affected_product_id,
    nullif(related_branch_id, '')                          as related_branch_id,
    nullif(origin_interaction_id, '')                       as origin_interaction_id,
    description,
    nullif(claimed_amount, '')::numeric(15,2)               as claimed_amount,
    nullif(currency, '')                                    as currency,
    priority,
    status,
    nullif(assigned_agent_id, '')                           as assigned_agent_id,
    nullif(assignment_date, '')::timestamp                  as assignment_date,
    nullif(first_response_date, '')::timestamp              as first_response_date,
    nullif(resolution_date, '')::timestamp                  as resolution_date,
    nullif(closing_date, '')::timestamp                     as closing_date,
    (sla_breached)::boolean                                  as sla_breached,
    nullif(resolution_days, '')::numeric::int                as resolution_days,
    nullif(resolution, '')                                  as resolution,
    nullif(compensation_granted, '')::numeric(15,2)         as compensation_granted,
    nullif(resolution_satisfaction, '')::numeric::int        as resolution_satisfaction,
    (is_repeat_complainer)::boolean                          as is_repeat_complainer
from source
