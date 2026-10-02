-- The tables the service created at startup before migrations existed. "if not exists" so it is a no-op on a
-- database that already has them (prod), and builds them on a fresh one.
create schema if not exists app;

create table if not exists app.disputes (
    case_id uuid primary key default gen_random_uuid(),
    customer_id text not null,
    transaction_id text not null,
    reason_code text not null,
    summary text not null,
    status text not null default 'open'
        check (status in ('open', 'auto_resolved', 'escalated', 'closed')),
    evidence jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    resolved_at timestamptz
);

create index if not exists disputes_customer_idx on app.disputes (customer_id, created_at desc);

create table if not exists app.dispute_events (
    id bigint generated always as identity primary key,
    case_id uuid not null references app.disputes (case_id),
    event text not null,
    payload jsonb not null default '{}'::jsonb,
    ts timestamptz not null default now()
);

create index if not exists dispute_events_case_idx on app.dispute_events (case_id, ts);
