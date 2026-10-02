-- One case per (customer, transaction): opening it again returns the existing one. Cases closed by an operator
-- do not count, so a transaction can be reported again after that.
--
-- Before the unique index can exist, older duplicates (the agent opened a new case on every attempt) are closed
-- and a "closed" event says why. The newest case of each pair stays.
with ranked as (
    select case_id,
           row_number() over (partition by customer_id, transaction_id order by created_at desc, case_id) as position
    from app.disputes
    where status <> 'closed'
),
closed as (
    update app.disputes d
    set status = 'closed', resolved_at = coalesce(d.resolved_at, now())
    from ranked r
    where d.case_id = r.case_id and r.position > 1
    returning d.case_id
)
insert into app.dispute_events (case_id, event, payload)
select case_id, 'closed', '{"reason": "duplicate of a newer case for the same transaction (migration 0003)"}'::jsonb
from closed;

alter table app.disputes add column if not exists idempotency_key text;

create unique index if not exists disputes_one_per_transaction
    on app.disputes (customer_id, transaction_id) where status <> 'closed';

create unique index if not exists disputes_idempotency_key
    on app.disputes (customer_id, idempotency_key) where idempotency_key is not null;
