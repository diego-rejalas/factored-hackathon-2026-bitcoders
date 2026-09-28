# data/dbt/ — dbt (bronze. → silver. → gold.)

Vertical 2 de `../../spec/ARCHITECTURE.md`. Transforma `bronze.*` (volcado por el DAG en `../dags/`) en `silver.*` y `gold.*` (lo que lee `../../backend/`), dentro de la base `data`.

Contenido de datos, no de infraestructura — la config de cómo se despliega (Airflow y dbt) vive aparte en `../../infra/`.

**dbt corre como su propio servicio Railway** (`../../infra/dbt/`, ver su README), no horneado en la imagen de Airflow — eso fue la primera versión, descartada por dos motivos: (1) los paquetes transitivos de `dbt-postgres` (`isodate`, `pathspec`) chocan con las versiones exactas que fija el archivo de constraints de Airflow 3.3.0, ninguna versión de dbt-postgres satisface ambos a la vez, y (2) el equipo quería dbt visible como pieza propia en el canvas de Railway, junto a Postgres y Airflow (grupo "Data Pipeline" en `../../.railway/railway.ts`). El DAG le pega por HTTP (`POST /run`) después de terminar la carga a `bronze.*` — no un cron suelto, para garantizar el orden.

## Estructura

- `models/staging/stg_*.sql` — cast de tipos reales, `''` → `NULL`, sin lógica de negocio. Vistas en el schema `silver`.
- `models/staging/sources.yml` — declara `bronze.*` como fuente, con los hallazgos de `../../spec/DATA_FINDINGS.md` documentados por tabla.
- `models/staging/schema.yml` — tests (`not_null`, `unique`, `accepted_values`, `relationships`) — son los "contratos de datos" que pide el reto.
- `models/clean/clean_*.sql` — tablas materializadas en el schema `gold`, lo que lee el tool layer (`backend/`). Por ahora son pass-through de silver (sin joins todavía) — los joins/agregaciones específicos de workflow se agregan cuando el equipo vote entre las opciones A/B/C/D.
- `models/clean/schema.yml` — mismos tests sobre la capa final.

## Decisiones de calidad de datos ya tomadas (no reinventar al escribir modelos nuevos)

- **`clean_transactions` excluye `is_fraud`/`fraud_score`** — son ground truth de evaluación, nunca input del agente (leakage). Si un modelo nuevo necesita fraude como feature, es un bug.
- **`currency` nunca corrige la ausencia de MXN** — se documenta como limitación de datos real (ver `../../spec/DATA_FINDINGS.md`), no se inventa una conversión.
- **`contact_reason`/`reason_category`** en `call_center_interactions` son el mismo campo en la práctica — no asumir que dan más granularidad de la real.

## Correr localmente

```bash
cd data/dbt
cp .env.example .env   # completar con las credenciales del Postgres de Railway
export $(cat .env | xargs)
dbt run
dbt test
```

## Great Expectations

Evaluado y descartado por ahora — se solapa con los tests de dbt de arriba (mismo tipo de chequeo: not_null, valores aceptados, unicidad). Lo único que aportaría es un reporte HTML (Data Docs) para el video pitch; si el equipo lo quiere por eso, agregar después, no reemplaza los tests de dbt.
