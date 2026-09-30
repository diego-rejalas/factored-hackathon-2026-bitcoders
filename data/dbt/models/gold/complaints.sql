{{ config(indexes=[
    {'columns': ['complaint_id'], 'unique': True},
    {'columns': ['customer_id']},
]) }}

select * from {{ ref('stg_complaints') }}
