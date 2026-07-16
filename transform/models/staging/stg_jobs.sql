with source as (
    select * from {{ source('raw', 'jobs') }}
),

cleaned as (
    select
        job_id,
        related_call_id,
        status                        as job_status,
        service_category,
        value::numeric(10,2)          as job_value,
        technician,
        scheduled_at::timestamp       as scheduled_at,
        nullif(completed_at, '')::timestamp as completed_at
    from source
    where job_id is not null
)

select * from cleaned
