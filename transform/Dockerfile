FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir dbt-core==1.8.7 dbt-postgres==1.8.2

COPY . .
RUN dbt deps --profiles-dir .

CMD ["dbt", "build", "--profiles-dir", "."]
