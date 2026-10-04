-- Marketing campaigns (200 rows). Not used in customer service.
-- Silver: real types, '' -> NULL, no business logic. See docs/DATA.md.
with source as (
    select * from {{ source('bronze', 'marketing_campaigns') }}
)

select
    campaign_id,
    campaign_name,
    nullif(description, '')                              as description,
    campaign_type,
    campaign_objective,
    nullif(promoted_product, '')                         as promoted_product,
    nullif(target_segment, '')                           as target_segment,
    {{ normalize_country("nullif(target_country, '')") }}  as target_country,
    nullif(start_date, '')::date                         as start_date,
    nullif(end_date, '')::date                           as end_date,
    nullif(budget, '')::numeric(15,2)                    as budget,
    campaign_status,
    {{ to_decimal('expected_conversion_rate') }}        as expected_conversion_rate
from source
