-- The specialist console (the admin side) needs three things the first tables did not have. Ported from the
-- statements the data layer used to run on every start, so the same change now has a version and runs once.
--   1. a case can exist without a transaction (an escalation that could not be tied to one);
--   2. a status for a case a specialist has taken ('in_progress');
--   3. an escalated case is not a resolved one: resolved_at is only for what was resolved.

alter table app.disputes alter column transaction_id drop not null;

-- Databases created before the console carry the old, unnamed CHECK that rejects 'in_progress'. Postgres named it
-- itself (usually disputes_status_check), so the stale one is found through pg_constraint instead of by name.
do $$
declare
    stale record;
begin
    for stale in
        select conname
        from pg_constraint
        where conrelid = 'app.disputes'::regclass
          and contype = 'c'
          and pg_get_constraintdef(oid) like '%status%'
          and pg_get_constraintdef(oid) not like '%in_progress%'
    loop
        execute format('alter table app.disputes drop constraint %I', stale.conname);
    end loop;
end
$$;

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conrelid = 'app.disputes'::regclass and conname = 'disputes_status_allowed'
    ) then
        alter table app.disputes
            add constraint disputes_status_allowed
            check (status in ('open', 'auto_resolved', 'escalated', 'in_progress', 'closed'));
    end if;
end
$$;

create index if not exists disputes_status_idx on app.disputes (status, created_at desc);

update app.disputes set resolved_at = null where status in ('escalated', 'in_progress');

-- Handoffs and event payloads that were stored as JSON text (the same repair as 0004, kept because it is idempotent
-- and the console's own tests expect it).
update app.disputes
set evidence = jsonb_set(evidence, '{handoff}', (evidence ->> 'handoff')::jsonb)
where jsonb_typeof(evidence -> 'handoff') = 'string' and btrim(evidence ->> 'handoff') like '{%';

update app.dispute_events
set payload = (payload #>> '{}')::jsonb
where jsonb_typeof(payload) = 'string' and btrim(payload #>> '{}') like '{%';
