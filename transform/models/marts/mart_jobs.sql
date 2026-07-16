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
        count(*)                                          as total_jobs,
        count(*) filter (where job_status = 'completed')  as completed,
        count(*) filter (where job_status = 'scheduled')  as scheduled,
        count(*) filter (where job_status = 'cancelled')  as cancelled,
        round(
            100.0 * count(*) filter (where job_status = 'completed')
            / nullif(count(*), 0), 1
        )                                                 as completion_rate_pct,
        round(avg(job_value) filter (where job_status = 'completed'), 2)
                                                          as avg_completed_value,
        round(sum(job_value) filter (where job_status = 'completed'), 2)
                                                          as total_completed_value
    from jobs
    group by 1
)

select * from by_category
order by total_completed_value desc
