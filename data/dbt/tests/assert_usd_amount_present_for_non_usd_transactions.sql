{{ config(severity='warn') }}
-- amount_usd is null for every USD transaction (the amount already is USD, so
-- that is expected) but also for ~5% of ARS/COP ones: those are real gaps.
select transaction_id, currency, amount
from {{ ref('stg_transactions') }}
where currency <> 'USD' and amount_usd is null
