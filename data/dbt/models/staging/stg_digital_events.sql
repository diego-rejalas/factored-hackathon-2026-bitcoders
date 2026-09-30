-- Eventos digitales (15.620.994). Sesiones anónimas: customer_id vacío en ~24%. ip_country se conforma a 'México'.
-- Silver: tipos reales, '' -> NULL, sin lógica de negocio. Ver spec/DATA_FINDINGS.md.
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
    nullif(event_value, '')::numeric            as event_value,
    nullif(duration_seconds, '')::numeric::int  as duration_seconds,
    nullif(ip_address, '')                      as ip_address,
    {{ normalize_country('ip_country') }}         as ip_country,
    nullif(ip_city, '')                         as ip_city,
    nullif(is_mobile, '')::boolean              as is_mobile,
    nullif(referrer, '')                        as referrer,
    nullif(utm_source, '')                      as utm_source,
    nullif(utm_medium, '')                      as utm_medium,
    nullif(utm_campaign, '')                    as utm_campaign
from source
