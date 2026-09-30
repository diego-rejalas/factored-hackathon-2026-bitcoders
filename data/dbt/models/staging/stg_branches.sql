-- Sucursales. Dimensión pequeña (350 filas) que habilita las pruebas de clave foránea a sucursal.
-- Silver: tipos reales, '' -> NULL, sin lógica de negocio. Ver spec/DATA_FINDINGS.md.
with source as (
    select * from {{ source('bronze', 'branches') }}
)

select
    branch_id,
    branch_code,
    branch_name,
    branch_type,
    address,
    city,
    state,
    country,
    postal_code,
    geographic_zone,
    phone,
    email,
    nullif(opening_time, '')::time                 as opening_time,
    nullif(closing_time, '')::time                 as closing_time,
    nullif(has_atms, '')::boolean                  as has_atms,
    {{ to_int('atm_count') }}            as atm_count,
    nullif(has_teller_windows, '')::boolean        as has_teller_windows,
    {{ to_int('teller_window_count') }}  as teller_window_count,
    nullif(latitude, '')::numeric(10,7)            as latitude,
    nullif(longitude, '')::numeric(10,7)           as longitude,
    nullif(branch_opening_date, '')::date          as branch_opening_date,
    branch_status
from source
