with source as (
    select * from {{ source('raw', 'stripe_payments') }}
),

cleaned as (
    select
        payment_id,
        timestamp::timestamp            as payment_timestamp,
        amount_cents::int               as amount_cents,
        round(amount_cents::numeric / 100, 2) as amount_dollars,
        currency,
        status,
        payment_method,
        customer_email,
        description                     as service_description,
        metadata_source
    from source
    where payment_id is not null
      and status != 'failed'
)

select * from cleaned
