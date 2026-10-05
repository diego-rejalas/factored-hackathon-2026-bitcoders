# data/dbt/ — dbt (bronze. → silver. → gold.)

Vertical 2 de `../../docs/ARCHITECTURE.md`. Transforma `bronze.*` (que carga el DAG `latam_bank_gcp` con DuckDB, ver `../../infra/gcp/airflow/`) en `silver.*` y `gold.*` (lo que lee `../../backend/`), dentro de la base `data` de Postgres.

Contenido de datos, no de infraestructura: cómo se despliega dbt vive en `../../infra/gcp/airflow/` (VM) y `../../infra/gcp/etl/` (Cloud Run Job).

**dbt corre dentro de la imagen de Airflow en GCP** (`dbt-duckdb`), no como servicio aparte. El proyecto también compila contra Postgres (`--target postgres`) para pruebas locales.

## Estructura

- `models/staging/stg_*.sql` — una vista por cada una de las 13 tablas de bronze: cast de tipos reales, `''` → `NULL`, sin lógica de negocio salvo conformar valores (`macros/normalize_country.sql` unifica 'Mexico' y 'México'). Vistas en el schema `silver`.
- `models/staging/sources.yml` — declara las 13 tablas de `bronze.*` como fuente, con los hallazgos de `../../docs/DATA.md` documentados por tabla.
- `models/staging/schema.yml` — tests (`not_null`, `unique`, `accepted_values`, `relationships`, `accepted_range`, `unique_combination`) — son los "contratos de datos" que pide el reto. Los defectos conocidos de los datos corren con `severity: warn`: no frenan la corrida, pero aparecen con su conteo en cada build.
- `tests/generic/` — tests genéricos propios (`accepted_range`, `unique_combination`); `tests/*.sql` — reglas de negocio (titularidad transacción-producto, defectos medidos de quejas, saldo sobre límite, etc.).
- `models/gold/<entidad>.sql` — tablas materializadas en el schema `gold`, lo que lee el tool layer (`backend/`). Sin prefijo `clean_`: medallion reserva la limpieza (casts, nulls) para silver — gold nombra por entidad/consumidor de negocio. Por ahora son pass-through de silver (sin joins todavía) — los joins/agregaciones específicos de workflow se agregan cuando el equipo vote entre las opciones A/B/C/D.
- `models/gold/schema.yml` — mismos tests sobre la capa final.

## Decisiones de calidad de datos ya tomadas (no reinventar al escribir modelos nuevos)

- **`gold.transactions` excluye `is_fraud`/`fraud_score`** — son ground truth de evaluación, nunca input del agente (leakage). Si un modelo nuevo necesita fraude como feature, es un bug.
- **`currency` nunca corrige la ausencia de MXN** — se documenta como limitación de datos real (ver `../../docs/DATA.md`), no se inventa una conversión.
- **`contact_reason`/`reason_category`** en `call_center_interactions` son el mismo campo en la práctica — no asumir que dan más granularidad de la real.

## Correr localmente

```bash
cd data/dbt
cp .env.example .env   # completar con las credenciales del Postgres local
export $(cat .env | xargs)
dbt build   # modelos + tests, cada modelo se prueba antes de construir lo que depende de él
```

Con el destino `postgres` necesita que `bronze.*` ya esté cargado en esa base. En GCP no hace falta: el DAG construye todo en memoria con `dbt-duckdb` y solo publica `gold.*`.

## Great Expectations

Evaluado y descartado por ahora — se solapa con los tests de dbt de arriba (mismo tipo de chequeo: not_null, valores aceptados, unicidad). Lo único que aportaría es un reporte HTML (Data Docs) para el video pitch; si el equipo lo quiere por eso, agregar después, no reemplaza los tests de dbt.
