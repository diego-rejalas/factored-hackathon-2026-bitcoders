{{ config(indexes=[
    {'columns': ['product_id'], 'unique': True},
    {'columns': ['customer_id']},
]) }}

select * from {{ ref('stg_products') }}
