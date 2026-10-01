-- Service agents (1,200 rows). 129 speak Portuguese: the only evidence of Portuguese in the dataset.
-- Silver: real types, '' -> NULL, no business logic. See spec/DATA_FINDINGS.md.
with source as (
    select * from {{ source('bronze', 'service_agents') }}
)

select
    agent_id,
    employee_code,
    first_name,
    last_name,
    email,
    nullif(phone, '')                                     as phone,
    native_accent,
    {{ normalize_country('country_of_origin') }}            as country_of_origin,
    nullif(assigned_branch_id, '')                        as assigned_branch_id,
    agent_type,
    experience_level,
    languages,
    nullif(specialty, '')                                 as specialty,
    nullif(hire_date, '')::date                           as hire_date,
    nullif(avg_csat, '')::numeric(4,2)                    as avg_csat,
    {{ to_int('total_monthly_interactions') }}  as total_monthly_interactions,
    agent_status,
    work_shift
from source
