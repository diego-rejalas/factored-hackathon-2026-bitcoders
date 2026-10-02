-- escalate_dispute passed a JSON string to a jsonb parameter whose codec already serializes, so every handoff was
-- stored as a JSON *string* holding JSON ("{\"request\": ...}") instead of an object. Unwrap them.
update app.disputes
set evidence = jsonb_set(evidence, '{handoff}', (evidence #>> '{handoff}')::jsonb)
where jsonb_typeof(evidence -> 'handoff') = 'string';

update app.dispute_events
set payload = (payload #>> '{}')::jsonb
where jsonb_typeof(payload) = 'string';
