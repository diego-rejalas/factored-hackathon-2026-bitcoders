# infra/dbt/ — dbt como servicio Railway propio

Deployment config para correr dbt como su propio servicio (visible aparte en el canvas de Railway, dentro del grupo "Data Pipeline" junto a Postgres y Airflow) — no horneado en la imagen de Airflow. El proyecto dbt real (modelos, tests) vive en `../../data/dbt/`, separado a propósito (ver `../../spec/ARCHITECTURE.md`).

## Por qué HTTP y no cron

Un cron propio en este servicio correría dbt en un horario fijo, sin garantía de que la ingesta (Airflow) ya haya terminado de cargar `raw.*`. En cambio: expone `POST /run` (FastAPI, `app.py`), y el DAG de ingesta en `../../data/dags/` le pega recién después de que la task de carga S3→`raw.*` termina bien — así el orden queda correcto sin acoplar los dos contenedores en un solo proceso.

## Endpoints

- `GET /health` — healthcheck de Railway.
- `POST /run` — corre `dbt run` y, si sale bien, `dbt test`. Devuelve `exit_code`/`stdout`/`stderr` de cada paso en el body (nunca lanza una excepción HTTP por un fallo de dbt — el caller decide qué hacer con `ok: false`).

## Variables de entorno

Las mismas de `../../data/dbt/.env.example` (`DBT_PG_HOST`, `DBT_PG_PORT`, `DBT_PG_USER`, `DBT_PG_PASSWORD`, `DBT_PG_DATABASE`), declaradas en `../../.railway/railway.ts` como referencia directa al servicio `Postgres` — nunca hardcodeadas.

## Cómo lo llama el DAG

```python
import requests

resp = requests.post(f"http://{os.environ['DBT_SERVICE_URL']}/run", timeout=600)
result = resp.json()
if not result["ok"]:
    raise AirflowException(result)
```

`DBT_SERVICE_URL` ya está declarado en `railwayapp-airflow` dentro de `../../.railway/railway.ts` (dominio privado del servicio `dbt`).
