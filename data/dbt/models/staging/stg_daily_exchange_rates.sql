-- Tipo de cambio diario por par de monedas (13.164). Incluye pares con MXN. La columna origen `date` se renombra a `rate_date`.
-- Silver: tipos reales, '' -> NULL, sin lógica de negocio. Ver spec/DATA_FINDINGS.md.
with source as (
    select * from {{ source('bronze', 'daily_exchange_rates') }}
)

select
    nullif("date", '')::date            as rate_date,
    source_currency,
    target_currency,
    nullif(exchange_rate, '')::numeric  as exchange_rate,
    nullif(buy_rate, '')::numeric       as buy_rate,
    nullif(sell_rate, '')::numeric      as sell_rate,
    source
from source
