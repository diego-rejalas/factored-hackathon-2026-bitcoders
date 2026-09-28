FROM python:3.12-slim

WORKDIR /app

COPY infra/dbt/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# The dbt project itself (models, tests) is data engineering content, not
# infra — lives in data/dbt/, this Dockerfile just runs it. Build context
# is the repo root so this path is reachable.
COPY data/dbt/ /app/dbt/
COPY infra/dbt/app.py /app/app.py

EXPOSE 8000
CMD uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}
