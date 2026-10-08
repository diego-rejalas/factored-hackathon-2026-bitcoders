FROM python:3.12-slim

WORKDIR /app

COPY infra/gcp/waker/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY infra/gcp/waker/app/ /app/app/
# Tests ship in the image so CI can run `python -m pytest` inside it (as root, to install pytest and httpx).
COPY infra/gcp/waker/tests/ /app/tests/

# Not root: the service only talks to Google APIs and needs no privileges.
RUN useradd --system --no-create-home waker
USER waker

EXPOSE 8080
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
