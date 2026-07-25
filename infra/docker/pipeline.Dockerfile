FROM python:3.12-slim

# Install Python deps for ingest + dbt + Dagster.
# dagster-dbt pins its matching dagster version, and that pair allows
# dbt-core >=1.7,<1.12, so the dbt pins below stay valid.
WORKDIR /app
COPY ingest/requirements.txt /app/ingest/requirements.txt
COPY orchestration/requirements.txt /app/orchestration/requirements.txt
RUN pip install --no-cache-dir -r /app/ingest/requirements.txt \
    && pip install --no-cache-dir dbt-core==1.8.7 dbt-postgres==1.8.2 dbt-redshift==1.8.1 \
    && pip install --no-cache-dir -r /app/orchestration/requirements.txt

# Copy source code
COPY ingest/ /app/ingest/
COPY transform/ /app/transform/
COPY orchestration/ /app/orchestration/
COPY scripts/ /app/scripts/

# Install dbt packages, then bake the manifest into the image. The Dagster code
# location loads the dbt asset graph from that manifest, so building it here
# means definitions load without a warehouse and without parsing on every boot.
RUN cd /app/transform && dbt deps --profiles-dir . && dbt parse --profiles-dir .

# Dagster writes run history, schedule ticks, and sensor cursors here. Compose
# mounts a volume over it so that state survives a restart.
ENV DAGSTER_HOME=/dagster_home
RUN mkdir -p /dagster_home
COPY infra/docker/dagster.yaml /dagster_home/dagster.yaml

RUN chmod +x /app/scripts/run_pipeline.sh
CMD ["/app/scripts/run_pipeline.sh"]
