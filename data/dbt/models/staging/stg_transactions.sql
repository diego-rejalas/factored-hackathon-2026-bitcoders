-- is_fraud/fraud_score are ground truth for evaluation only — see
-- docs/DATA.md. Kept here (silver mirrors bronze with real types);
-- any model the agent/tool layer reads from must NOT expose these as
-- input signal, only gold./eval-set consumers should.
with source as (
    select * from {{ source('bronze', 'transactions') }}
)

select
    transaction_id,
    transaction_date::timestamp                           as transaction_date,
    process_date::date                                    as process_date,
    product_id,
    customer_id,
    transaction_type,
    transaction_category,
    amount::numeric(15,2)                                 as amount,
    currency,
    nullif(amount_usd, '')::numeric(15,2)                 as amount_usd,
    channel,
    nullif(branch_id, '')                                  as branch_id,
    nullif(merchant_name, '')                              as merchant_name,
    nullif(merchant_category, '')                          as merchant_category,
    transaction_country,
    nullif(transaction_city, '')                           as transaction_city,
    transaction_status,
    nullif(response_code, '')                              as response_code,
    (is_fraud)::boolean                                     as is_fraud,
    nullif(fraud_score, '')::numeric(5,2)                   as fraud_score,
    nullif(latitude, '')::numeric(10,7)                     as latitude,
    nullif(longitude, '')::numeric(10,7)                    as longitude
from source
