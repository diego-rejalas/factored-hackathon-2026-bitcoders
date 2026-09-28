-- contact_reason == reason_category in practice (same 6 values, see
-- spec/DATA_FINDINGS.md) — kept as two columns for schema fidelity, don't
-- expect extra granularity from contact_reason downstream.
with source as (
    select * from {{ source('bronze', 'call_center_interactions') }}
)

select
    interaction_id,
    interaction_date::timestamp                            as interaction_date,
    process_date::date                                     as process_date,
    customer_id,
    nullif(agent_id, '')                                    as agent_id,
    interaction_type,
    channel,
    contact_reason,
    reason_category,
    nullif(duration_seconds, '')::int                       as duration_seconds,
    nullif(wait_time_seconds, '')::int                      as wait_time_seconds,
    nullif(was_resolved, '')::boolean                       as was_resolved,
    (requires_followup)::boolean                             as requires_followup,
    nullif(detected_sentiment, '')                          as detected_sentiment,
    nullif(sentiment_score, '')::numeric(3,2)                as sentiment_score,
    nullif(customer_detected_accent, '')                     as customer_detected_accent,
    nullif(agent_used_accent, '')                            as agent_used_accent,
    (was_escalated)::boolean                                  as was_escalated,
    nullif(mentioned_products, '')                           as mentioned_products,
    (has_transcript)::boolean                                 as has_transcript,
    (has_recording)::boolean                                  as has_recording
from source
