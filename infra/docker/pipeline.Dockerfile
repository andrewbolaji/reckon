FROM python:3.12-slim

# Install Python deps for ingest + dbt
WORKDIR /app
COPY ingest/requirements.txt /app/ingest/requirements.txt
RUN pip install --no-cache-dir -r /app/ingest/requirements.txt \
    && pip install --no-cache-dir dbt-core==1.8.7 dbt-postgres==1.8.2 dbt-redshift==1.8.1

# Copy source code
COPY ingest/ /app/ingest/
COPY transform/ /app/transform/
COPY scripts/ /app/scripts/

# Install dbt packages
RUN cd /app/transform && dbt deps --profiles-dir .

RUN chmod +x /app/scripts/run_pipeline.sh
CMD ["/app/scripts/run_pipeline.sh"]
