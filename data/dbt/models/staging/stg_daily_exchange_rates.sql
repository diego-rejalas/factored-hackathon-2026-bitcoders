-- Daily exchange rate per currency pair (13,164 rows). Includes MXN pairs. The source column `date` is renamed to `rate_date`.
-- Silver: real types, '' -> NULL, no business logic. See spec/DATA_FINDINGS.md.
with source as (
    select * from {{ source('bronze', 'daily_exchange_rates') }}
)

select
    nullif("date", '')::date            as rate_date,
    source_currency,
    target_currency,
    {{ to_decimal('exchange_rate') }}  as exchange_rate,
    {{ to_decimal('buy_rate') }}       as buy_rate,
    {{ to_decimal('sell_rate') }}      as sell_rate,
    source
from source
