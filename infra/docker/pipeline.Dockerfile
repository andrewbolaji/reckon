FROM python:3.12-slim

# Install Python deps for ingest + dbt + Dagster.
# dagster-dbt pins its matching dagster version, and that pair allows
# dbt-core >=1.7,<1.12, so the dbt pins below stay valid.
#
# One pip install call, not three sequential ones. dbt's own dependencies cap
# protobuf below 5.0; dagster pulls in grpcio-health-checking with no pin of
# its own, and a *separate* `pip install` for it doesn't re-resolve against
# constraints from an earlier call, so it can land on a release that needs a
# newer protobuf than dbt allows. Reproduced locally: split calls in this
# exact order still resolved an incompatible pair even though dbt already
# went first, one resolver call across everything is what actually fixes it.
WORKDIR /app
COPY ingest/requirements.txt /app/ingest/requirements.txt
COPY orchestration/requirements.txt /app/orchestration/requirements.txt
RUN pip install --no-cache-dir -r /app/ingest/requirements.txt -r /app/orchestration/requirements.txt \
    dbt-core==1.8.7 dbt-postgres==1.8.2 dbt-redshift==1.8.1

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
