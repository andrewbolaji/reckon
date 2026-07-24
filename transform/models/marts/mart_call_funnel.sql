/*
  Call Funnel Mart
  Aggregates Aria call data into a daily funnel:
  total calls -> qualified -> booked, plus escalation and miss rates.
  Enriched with job completion counts from the jobs source.
*/

with calls as (
    select * from {{ ref('stg_aria_calls') }}
),

jobs_agg as (
    -- Aggregate jobs to the daily-call grain before joining
    -- so there is no fanout even if the relationship becomes one-to-many.
    select
        c.call_timestamp::date as call_date,
        count(j.job_id)                                                     as total_jobs,
        count(case when j.job_status = 'completed' then j.job_id end)        as completed_jobs,
        count(case when j.job_status = 'cancelled' then j.job_id end)        as cancelled_jobs
    from calls c
    left join {{ ref('stg_jobs') }} j
        on c.call_id = j.related_call_id
    group by 1
),

daily as (
    select
        date_trunc('day', call_timestamp)::date as call_date,
        count(*)                                           as total_calls,
        count(case when outcome = 'qualified' then 1 end)  as qualified,
        count(case when outcome = 'booked' then 1 end)     as booked,
        count(case when outcome = 'escalated' then 1 end)  as escalated,
        count(case when outcome = 'missed' then 1 end)     as missed,
        count(case when outcome = 'resolved' then 1 end)   as resolved,
        round(avg(duration_seconds), 1)                as avg_duration_seconds,
        round(avg(sentiment_score), 2)                 as avg_sentiment
    from calls
    group by 1
)

select
    d.call_date,
    d.total_calls,
    d.qualified,
    d.booked,
    d.escalated,
    d.missed,
    d.resolved,
    d.avg_duration_seconds,
    d.avg_sentiment,
    round(100.0 * d.booked / nullif(d.total_calls, 0), 1)    as booking_rate_pct,
    round(100.0 * d.escalated / nullif(d.total_calls, 0), 1) as escalation_rate_pct,
    round(100.0 * d.missed / nullif(d.total_calls, 0), 1)    as miss_rate_pct,
    coalesce(j.total_jobs, 0)      as total_jobs,
    coalesce(j.completed_jobs, 0)  as completed_jobs,
    coalesce(j.cancelled_jobs, 0)  as cancelled_jobs
from daily d
left join jobs_agg j on d.call_date = j.call_date
order by d.call_date
