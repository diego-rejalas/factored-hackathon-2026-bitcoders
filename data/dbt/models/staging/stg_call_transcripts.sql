-- Call transcripts (171,321). Templated, 100% Spanish text: not usable to train an intent classifier.
-- Silver: real types, '' -> NULL, no business logic. See docs/DATA.md.
with source as (
    select * from {{ source('bronze', 'call_transcripts') }}
)

select
    transcript_id,
    interaction_id,
    nullif(process_date, '')::date              as process_date,
    customer_id,
    agent_id,
    full_text,
    customer_text,
    agent_text,
    detected_language,
    nullif(detected_accent, '')                 as detected_accent,
    {{ to_decimal('accent_confidence') }}      as accent_confidence,
    nullif(detected_keywords, '')               as detected_keywords,
    nullif(mentioned_entities, '')              as mentioned_entities,
    nullif(detected_intents, '')                as detected_intents,
    main_topics,
    transcription_model,
    nullif(audio_quality, '')                   as audio_quality,
    {{ to_int('duration_seconds') }}  as duration_seconds
from source
