{{ config(severity='warn') }}
-- KNOWN DATA DEFECT, measured not fixed: complaints.affected_product_id points
-- at another customer's product in 100% of the rows that have one (random
-- assignment, not recoverable — see docs/DATA.md). Kept as a warning
-- so the defect stays visible on every build; never use this field to show or
-- authorize product information.
select c.complaint_id, c.customer_id, c.affected_product_id, p.customer_id as product_owner
from {{ ref('stg_complaints') }} c
join {{ ref('stg_products') }} p on p.product_id = c.affected_product_id
where p.customer_id <> c.customer_id
