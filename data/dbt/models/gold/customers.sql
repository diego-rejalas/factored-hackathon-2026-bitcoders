{{ config(indexes=[{'columns': ['customer_id'], 'unique': True}]) }}

select * from {{ ref('stg_customers') }}
