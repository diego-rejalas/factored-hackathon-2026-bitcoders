FROM python:3.12-slim

WORKDIR /app

COPY agent/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY agent/app/ /app/app/
# Tests ship in the image so CI can run `python -m pytest` inside it.
COPY agent/tests/ /app/tests/
# The evaluation harness: its own logic is tested with the suite (tests/test_eval_*.py).
COPY agent/eval/ /app/eval/

EXPOSE 8000
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
