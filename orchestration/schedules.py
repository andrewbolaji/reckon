"""One schedule, materialising the whole DAG.

This is what replaces the cron entry. It is built from the partitioned job, so
each tick targets the most recent daily partition and Dagster records which
partition that run filled, which is what makes a missed day something you can
see and refill rather than something you have to notice.
"""

from dagster import DefaultScheduleStatus, build_schedule_from_partitioned_job

from orchestration.jobs import reckon_full_refresh

# 06:00 daily, matching the operational intent of the old CronJob: land the
# previous day well before anyone opens the dashboard. Running by default,
# same as the cron entry it replaces was: nothing had to be switched on by
# hand for the old script to run either.
reckon_daily_schedule = build_schedule_from_partitioned_job(
    reckon_full_refresh,
    name="reckon_daily_schedule",
    description="Materialise the full Reckon DAG once a day.",
    hour_of_day=6,
    default_status=DefaultScheduleStatus.RUNNING,
)

all_schedules = [reckon_daily_schedule]
