/*
  Call Funnel Mart
  Aggregates Aria call data into a daily funnel:
  total calls -> qualified -> booked, plus escalation and miss rates.
*/

with calls as (
    select * from {{ ref('stg_aria_calls') }}
),

daily as (
    select
        date_trunc('day', call_timestamp)::date as call_date,
        count(*)                                as total_calls,
        count(*) filter (where outcome = 'qualified')  as qualified,
        count(*) filter (where outcome = 'booked')     as booked,
        count(*) filter (where outcome = 'escalated')  as escalated,
        count(*) filter (where outcome = 'missed')     as missed,
        count(*) filter (where outcome = 'resolved')   as resolved,
        round(avg(duration_seconds), 1)                as avg_duration_seconds,
        round(avg(sentiment_score), 2)                 as avg_sentiment
    from calls
    group by 1
)

select
    call_date,
    total_calls,
    qualified,
    booked,
    escalated,
    missed,
    resolved,
    avg_duration_seconds,
    avg_sentiment,
    round(100.0 * booked / nullif(total_calls, 0), 1)    as booking_rate_pct,
    round(100.0 * escalated / nullif(total_calls, 0), 1) as escalation_rate_pct,
    round(100.0 * missed / nullif(total_calls, 0), 1)    as miss_rate_pct
from daily
order by call_date
