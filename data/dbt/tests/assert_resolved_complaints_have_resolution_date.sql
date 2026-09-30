{{ config(severity='warn') }}
-- KNOWN DATA QUIRK: ~770 complaints are Resolved/Closed with no resolution_date.
select complaint_id, status
from {{ ref('stg_complaints') }}
where status in ('Resolved', 'Closed') and resolution_date is null
