-- Satisfaction surveys (212,759 rows). main_score runs 1 to 7 across CSAT, NPS and CES; nps_category never contains Promoter.
-- Silver: real types, '' -> NULL, no business logic. See spec/DATA_FINDINGS.md.
with source as (
    select * from {{ source('bronze', 'satisfaction_surveys') }}
)

select
    survey_id,
    nullif(survey_date, '')::timestamp             as survey_date,
    nullif(process_date, '')::date                 as process_date,
    interaction_id,
    customer_id,
    agent_id,
    survey_type,
    send_channel,
    {{ to_int('main_score') }}           as main_score,
    nullif(nps_category, '')                       as nps_category,
    nullif(question_1_text, '')                    as question_1_text,
    {{ to_int('question_1_response') }}  as question_1_response,
    nullif(question_2_text, '')                    as question_2_text,
    {{ to_int('question_2_response') }}  as question_2_response,
    nullif(question_3_text, '')                    as question_3_text,
    {{ to_int('question_3_response') }}  as question_3_response,
    nullif(open_comments, '')                      as open_comments,
    nullif(comment_sentiment, '')                  as comment_sentiment,
    {{ to_decimal('response_time_hours') }}       as response_time_hours,
    {{ to_decimal('campaign_response_rate') }}    as campaign_response_rate
from source
