FROM python:3.12-slim

WORKDIR /app

COPY etl/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Fetch the DuckDB extensions at build time so the job never depends on
# extensions.duckdb.org being reachable when it runs.
RUN python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL httpfs'); c.execute('INSTALL postgres')"

# The dbt project is data engineering content that lives in data/dbt/; the
# build context is the repo root so it is reachable here.
COPY data/dbt/ /app/dbt/
COPY etl/run.py /app/run.py

CMD ["python", "-u", "run.py"]
