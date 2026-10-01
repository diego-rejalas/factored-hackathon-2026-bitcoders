{{ config(indexes=[
    {'columns': ['customer_id']},
]) }}

select * from {{ ref('stg_complaints') }}
