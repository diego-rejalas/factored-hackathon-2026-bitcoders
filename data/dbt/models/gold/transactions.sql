{{ config(indexes=[
    {'columns': ['transaction_id'], 'unique': True},
    {'columns': ['customer_id', 'transaction_date']},
    {'columns': ['product_id']},
]) }}

-- is_fraud/fraud_score deliberately excluded: this is what backend/ (the
-- tool layer) reads from. Ground truth stays only in stg_transactions /
-- the eval dataset, never as input the agent or its tools can see.
select
    transaction_id,
    transaction_date,
    process_date,
    product_id,
    customer_id,
    transaction_type,
    transaction_category,
    amount,
    currency,
    amount_usd,
    channel,
    branch_id,
    merchant_name,
    merchant_category,
    transaction_country,
    transaction_city,
    transaction_status,
    response_code,
    latitude,
    longitude
from {{ ref('stg_transactions') }}
