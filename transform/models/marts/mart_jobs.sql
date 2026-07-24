/*
  Jobs Mart
  Completion rate and revenue per completed job, by service category.
*/

with jobs as (
    select * from {{ ref('stg_jobs') }}
),

by_category as (
    select
        service_category,
        count(*)                                                 as total_jobs,
        count(case when job_status = 'completed' then 1 end)     as completed,
        count(case when job_status = 'scheduled' then 1 end)     as scheduled,
        count(case when job_status = 'cancelled' then 1 end)     as cancelled,
        round(
            100.0 * count(case when job_status = 'completed' then 1 end)
            / nullif(count(*), 0), 1
        )                                                        as completion_rate_pct,
        round(avg(case when job_status = 'completed' then job_value end), 2)
                                                                 as avg_completed_value,
        round(sum(case when job_status = 'completed' then job_value end), 2)
                                                                 as total_completed_value
    from jobs
    group by 1
)

select * from by_category
order by total_completed_value desc
