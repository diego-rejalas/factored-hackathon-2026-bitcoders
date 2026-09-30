{{ config(indexes=[
    {'columns': ['interaction_id'], 'unique': True},
    {'columns': ['customer_id']},
]) }}

select * from {{ ref('stg_call_center_interactions') }}
