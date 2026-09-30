{{ config(severity='warn') }}
-- process_date - transaction_date is 0 or -1 day today (the -1 is a date-boundary /
-- timezone artifact), never positive: there are no late arrivals. Warn if that changes.
select transaction_id, transaction_date, process_date
from {{ ref('stg_transactions') }}
where abs(process_date - transaction_date::date) > 1
