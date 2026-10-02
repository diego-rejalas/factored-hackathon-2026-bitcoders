-- Login by user name and password. Only a hash is stored. A customer without a row here cannot sign in with a
-- password (the legacy customer_id + document login still works for the agent's own tests).
create table if not exists app.credentials (
    customer_id text primary key,
    username text not null,
    password_hash text not null,
    failed_attempts integer not null default 0,
    locked_until timestamptz,
    -- Demonstration accounts only: what the account shows, listed on the sign-in page.
    demo_label text,
    demo_hint text,
    created_at timestamptz not null default now(),
    password_changed_at timestamptz not null default now()
);

create unique index if not exists credentials_username_key on app.credentials (lower(username));
