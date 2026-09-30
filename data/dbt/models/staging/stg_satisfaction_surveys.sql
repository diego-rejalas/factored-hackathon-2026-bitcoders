-- Encuestas de satisfacción (212.759). main_score va de 1 a 7 para CSAT, NPS y CES; nps_category nunca trae Promoter.
-- Silver: tipos reales, '' -> NULL, sin lógica de negocio. Ver spec/DATA_FINDINGS.md.
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
    nullif(main_score, '')::numeric::int           as main_score,
    nullif(nps_category, '')                       as nps_category,
    nullif(question_1_text, '')                    as question_1_text,
    nullif(question_1_response, '')::numeric::int  as question_1_response,
    nullif(question_2_text, '')                    as question_2_text,
    nullif(question_2_response, '')::numeric::int  as question_2_response,
    nullif(question_3_text, '')                    as question_3_text,
    nullif(question_3_response, '')::numeric::int  as question_3_response,
    nullif(open_comments, '')                      as open_comments,
    nullif(comment_sentiment, '')                  as comment_sentiment,
    nullif(response_time_hours, '')::numeric       as response_time_hours,
    nullif(campaign_response_rate, '')::numeric    as campaign_response_rate
from source
