-- Local development data. NOT the organizer's rows: three invented customers that carry the ids, document numbers
-- and amounts infra/gcp/scripts/e2e.py checks the agent with, so each path of the dispute policy can be tried:
--   Ana   CLI-00MT1OY089RA  declined 4189.18 USD (over the threshold, escalates), reversed 2514.48, approved 6783.64
--   Bruno CLI-0064RNKCVQCN  declined 256.10 USD (under the threshold, resolves)
--   Carla CLI-00232W4ZDQPP  reversed 389.87 USD (under the threshold, resolves)
-- Same column types the dbt gold models produce. Loaded by Postgres on the first start of the dev database.

create schema gold;

create table gold.customers (
    customer_id text primary key, document_number text, first_name text, last_name text, country text
);
create table gold.products (
    product_id text primary key, customer_id text, product_type text, product_number text, currency text,
    current_balance numeric(15,2), credit_limit numeric(15,2), interest_rate numeric(5,2), opening_date date,
    product_status text, days_past_due int, last_transaction_date timestamp
);
create table gold.transactions (
    transaction_id text primary key, transaction_date timestamp, process_date date, product_id text, customer_id text,
    transaction_type text, transaction_category text, amount numeric(15,2), currency text, amount_usd numeric(15,2),
    channel text, branch_id text, merchant_name text, merchant_category text, transaction_country text,
    transaction_city text, transaction_status text, response_code text
);

insert into gold.customers values
    ('CLI-00MT1OY089RA', '17521506',   'Ana',   'Demo', 'Colombia'),
    ('CLI-0064RNKCVQCN', '0863503738', 'Bruno', 'Demo', 'Argentina'),
    ('CLI-00232W4ZDQPP', '57064351',   'Carla', 'Demo', 'México');

insert into gold.products values
    ('PRD-ANA-SAV', 'CLI-00MT1OY089RA', 'Cuenta Ahorro',    '4000111122223333', 'USD', 18250.40, null,    null,  '2019-03-12', 'Active', null, '2026-06-20 18:30:00'),
    ('PRD-ANA-CC',  'CLI-00MT1OY089RA', 'Tarjeta Crédito',  '5100222233334444', 'USD',  3200.00, 12000.00, 24.5, '2021-07-01', 'Active', 0,    '2026-06-21 09:10:00'),
    ('PRD-ANA-OLD', 'CLI-00MT1OY089RA', 'Cuenta Corriente', '4000999988887777', 'USD',     0.00, null,    null,  '2015-01-20', 'Closed', null, '2022-02-01 10:00:00'),
    ('PRD-BRU-SAV', 'CLI-0064RNKCVQCN', 'Cuenta Ahorro',    '4000555566667777', 'USD',   940.75, null,    null,  '2022-05-30', 'Active', null, '2026-06-18 12:00:00'),
    ('PRD-BRU-DEB', 'CLI-0064RNKCVQCN', 'Tarjeta Débito',   '5200111122220001', 'USD',     0.00, null,    null,  '2022-06-02', 'Active', null, '2026-06-19 15:45:00'),
    ('PRD-CAR-SAV', 'CLI-00232W4ZDQPP', 'Cuenta Ahorro',    '4000333344445555', 'USD',  5120.00, null,    null,  '2020-11-08', 'Active', null, '2026-06-17 08:20:00');

-- The scenario rows, then a few more so the history has something to page and filter.
insert into gold.transactions values
    ('TXN-ANA-001', '2026-06-20 18:30:00', '2026-06-20', 'PRD-ANA-CC',  'CLI-00MT1OY089RA', 'Purchase', 'Electronics', 4189.18, 'USD', 4189.18, 'Online', null, 'ElectroMundo',        'Electronics', 'Colombia', 'Bogotá',   'Declined', '51'),
    ('TXN-ANA-002', '2026-06-18 11:05:00', '2026-06-18', 'PRD-ANA-CC',  'CLI-00MT1OY089RA', 'Purchase', 'Travel',      2514.48, 'USD', 2514.48, 'Online', null, 'Aerolíneas del Sur',  'Travel',      'Colombia', 'Bogotá',   'Reversed', '00'),
    ('TXN-ANA-003', '2026-06-15 20:40:00', '2026-06-15', 'PRD-ANA-SAV', 'CLI-00MT1OY089RA', 'Transfer', 'Transfer',    6783.64, 'USD', 6783.64, 'App',    null, 'Transferencia externa','Transfer',   'Colombia', 'Medellín', 'Approved', '00'),
    ('TXN-ANA-004', '2026-06-14 09:15:00', '2026-06-14', 'PRD-ANA-CC',  'CLI-00MT1OY089RA', 'Purchase', 'Groceries',     84.20, 'USD',   84.20, 'POS',    null, 'Supermercado Central', 'Groceries',  'Colombia', 'Bogotá',   'Approved', '00'),
    ('TXN-ANA-005', '2026-06-12 13:00:00', '2026-06-12', 'PRD-ANA-CC',  'CLI-00MT1OY089RA', 'Purchase', 'Restaurants',   46.90, 'USD',   46.90, 'POS',    null, 'Café Andino',          'Restaurants','Colombia', 'Bogotá',   'Approved', '00'),
    ('TXN-ANA-006', '2026-06-10 19:25:00', '2026-06-10', 'PRD-ANA-SAV', 'CLI-00MT1OY089RA', 'Payment',  'Utilities',     63.15, 'USD',   63.15, 'App',    null, 'Empresa de Energía',   'Utilities',  'Colombia', 'Bogotá',   'Approved', '00'),
    ('TXN-ANA-007', '2026-06-08 08:50:00', '2026-06-08', 'PRD-ANA-CC',  'CLI-00MT1OY089RA', 'Purchase', 'Pharmacy',      27.45, 'USD',   27.45, 'POS',    null, 'Farmacia Salud',       'Pharmacy',   'Colombia', 'Bogotá',   'Approved', '00'),
    ('TXN-ANA-008', '2026-06-05 16:10:00', '2026-06-05', 'PRD-ANA-CC',  'CLI-00MT1OY089RA', 'Purchase', 'Fuel',          52.00, 'USD',   52.00, 'POS',    null, 'Estación Norte',       'Fuel',       'Colombia', 'Cali',     'Approved', '00'),
    ('TXN-BRU-001', '2026-06-19 15:45:00', '2026-06-19', 'PRD-BRU-DEB', 'CLI-0064RNKCVQCN', 'Purchase', 'Retail',       256.10, 'USD',  256.10, 'POS',    null, 'Tienda Don Pepe',      'Retail',     'Argentina','Córdoba',  'Declined', '51'),
    ('TXN-BRU-002', '2026-06-17 10:30:00', '2026-06-17', 'PRD-BRU-DEB', 'CLI-0064RNKCVQCN', 'Purchase', 'Groceries',     38.60, 'USD',   38.60, 'POS',    null, 'Mercado Los Andes',    'Groceries',  'Argentina','Córdoba',  'Approved', '00'),
    ('TXN-BRU-003', '2026-06-16 21:05:00', '2026-06-16', 'PRD-BRU-SAV', 'CLI-0064RNKCVQCN', 'Payment',  'Utilities',     29.99, 'USD',   29.99, 'App',    null, 'Telefonía Móvil',      'Utilities',  'Argentina','Córdoba',  'Approved', '00'),
    ('TXN-CAR-001', '2026-06-17 08:20:00', '2026-06-17', 'PRD-CAR-SAV', 'CLI-00232W4ZDQPP', 'Purchase', 'Retail',       389.87, 'USD',  389.87, 'Online', null, 'Moda Express',         'Retail',     'México',   'Monterrey','Reversed', '00'),
    ('TXN-CAR-002', '2026-06-13 12:40:00', '2026-06-13', 'PRD-CAR-SAV', 'CLI-00232W4ZDQPP', 'Purchase', 'Restaurants',   71.30, 'USD',   71.30, 'POS',    null, 'Taquería La Esquina',  'Restaurants','México',   'Monterrey','Approved', '00');
