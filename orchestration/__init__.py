"""Dagster orchestration for the Reckon pipeline.

The three source ingestions and every dbt model are software-defined assets in
one graph, so a failed extract visibly halts its own downstream models instead
of letting dbt rebuild marts on stale raw data.
"""
