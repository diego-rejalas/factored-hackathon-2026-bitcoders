-- Envíos de campañas (1.746.801, 1.083 días). Sin uso en atención al cliente.
-- Silver: tipos reales, '' -> NULL, sin lógica de negocio. Ver spec/DATA_FINDINGS.md.
with source as (
    select * from {{ source('bronze', 'campaign_sends') }}
)

select
    send_id,
    nullif(send_date, '')::timestamp             as send_date,
    nullif(process_date, '')::date               as process_date,
    campaign_id,
    customer_id,
    send_channel,
    nullif(template_used, '')                    as template_used,
    nullif(subject, '')                          as subject,
    send_status,
    nullif(was_delivered, '')::boolean           as was_delivered,
    nullif(was_opened, '')::boolean              as was_opened,
    nullif(open_date, '')::timestamp             as open_date,
    nullif(was_clicked, '')::boolean             as was_clicked,
    nullif(click_date, '')::timestamp            as click_date,
    {{ to_int('click_count') }}        as click_count,
    nullif(had_conversion, '')::boolean          as had_conversion,
    nullif(conversion_date, '')::timestamp       as conversion_date,
    nullif(conversion_value, '')::numeric(15,2)  as conversion_value,
    nullif(open_device, '')                      as open_device,
    nullif(open_country, '')                     as open_country,
    nullif(failure_reason, '')                   as failure_reason,
    {{ to_decimal('send_cost') }}               as send_cost
from source
