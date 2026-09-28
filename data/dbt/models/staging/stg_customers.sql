-- bronze.customers columns are text (ingestion loads CSVs as-is, see
-- spec/ARCHITECTURE.md vertical 1). Casts + empty-string-to-null happen once,
-- here, so every downstream model and the tool layer see real types.
with source as (
    select * from {{ source('bronze', 'customers') }}
)

select
    customer_id,
    nullif(document_number, '')                        as document_number,
    nullif(document_type, '')                           as document_type,
    first_name,
    last_name,
    nullif(date_of_birth, '')::date                     as date_of_birth,
    nullif(gender, '')                                  as gender,
    nullif(email, '')                                   as email,
    nullif(mobile_phone, '')                             as mobile_phone,
    nullif(landline_phone, '')                           as landline_phone,
    nullif(address, '')                                 as address,
    city,
    state,
    country,
    nullif(postal_code, '')                              as postal_code,
    nullif(detected_accent, '')                          as detected_accent,
    segment,
    nullif(credit_score, '')::numeric::int                as credit_score,
    nullif(estimated_monthly_income, '')::numeric(12,2)   as estimated_monthly_income,
    nullif(occupation, '')                               as occupation,
    nullif(marital_status, '')                           as marital_status,
    nullif(education_level, '')                          as education_level,
    registration_date::timestamp                        as registration_date,
    registration_branch_id,
    customer_status,
    last_updated::timestamp                              as last_updated,
    (accepts_marketing)::boolean                          as accepts_marketing
from source
