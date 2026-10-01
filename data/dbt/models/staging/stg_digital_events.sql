-- Digital events (15,620,994 rows). Anonymous sessions: customer_id is empty in ~24%. ip_country is conformed to 'México'.
-- Silver: real types, '' -> NULL, no business logic. See spec/DATA_FINDINGS.md.
with source as (
    select * from {{ source('bronze', 'digital_events') }}
)

select
    event_id,
    nullif(event_date, '')::timestamp           as event_date,
    nullif(process_date, '')::date              as process_date,
    nullif(customer_id, '')                     as customer_id,
    session_id,
    event_type,
    event_category,
    channel,
    nullif(platform, '')                        as platform,
    nullif(browser, '')                         as browser,
    nullif(app_version, '')                     as app_version,
    nullif(page_url, '')                        as page_url,
    nullif(page_title, '')                      as page_title,
    nullif(action, '')                          as action,
    nullif(element_id, '')                      as element_id,
    nullif(product_id, '')                      as product_id,
    {{ to_decimal('event_value') }}            as event_value,
    {{ to_int('duration_seconds') }}  as duration_seconds,
    nullif(ip_address, '')                      as ip_address,
    {{ normalize_country('ip_country') }}         as ip_country,
    nullif(ip_city, '')                         as ip_city,
    nullif(is_mobile, '')::boolean              as is_mobile,
    nullif(referrer, '')                        as referrer,
    nullif(utm_source, '')                      as utm_source,
    nullif(utm_medium, '')                      as utm_medium,
    nullif(utm_campaign, '')                    as utm_campaign
from source
