-- Currency gap (products.currency has zero MXN despite ~50% of customers
-- being Mexican) is NOT corrected here — documented in spec/DATA_FINDINGS.md
-- as a limitation to report, not silently patched.
with source as (
    select * from {{ source('raw', 'products') }}
)

select
    product_id,
    customer_id,
    product_type,
    product_number,
    currency,
    current_balance::numeric(15,2)                       as current_balance,
    nullif(credit_limit, '')::numeric(15,2)               as credit_limit,
    nullif(interest_rate, '')::numeric(5,2)               as interest_rate,
    opening_date::date                                    as opening_date,
    nullif(expiration_date, '')::date                     as expiration_date,
    opening_branch_id,
    product_status,
    opening_channel,
    (has_linked_app)::boolean                              as has_linked_app,
    nullif(days_past_due, '')::int                         as days_past_due,
    nullif(last_transaction_date, '')::timestamp           as last_transaction_date,
    last_updated::timestamp                               as last_updated
from source
