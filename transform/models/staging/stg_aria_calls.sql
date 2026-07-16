with source as (
    select * from {{ source('raw', 'aria_calls') }}
),

cleaned as (
    select
        call_id,
        timestamp::timestamp          as call_timestamp,
        caller_name,
        caller_phone,
        urgency,
        topic,
        outcome,
        duration_seconds::int         as duration_seconds,
        sentiment_score::numeric(3,2) as sentiment_score,
        agent_id
    from source
    where call_id is not null
      and timestamp is not null
)

select * from cleaned
