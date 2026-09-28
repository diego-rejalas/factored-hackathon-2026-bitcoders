# Despliegue de Airflow — mapeo completo

Estado real en Railway (proyecto `factored-hackathon`, servicio `airflow`), gestionado como código en `../.railway/railway.ts` (ver `ARCHITECTURE.md`, sección "Configuración de Railway como código"). El fork suelto `diego-rejalas/railwayapp-airflow-private` (fix original) quedó solo como referencia — la fuente real es este repo.

## Fuente

- Repo: `diego-rejalas/factored-hackathon-2026-bitcoders` (el del equipo).
- Rama: `main`.
- Build context: raíz del repo (no `infra/airflow/`) — necesario para que el Dockerfile pueda copiar `data/dags/` y `data/dbt/`.
- `dockerfilePath`: `infra/airflow/Dockerfile`.
- Deployment config (Dockerfile, entrypoint, `.env.example`) vive en `../infra/airflow/`; el DAG real y el proyecto dbt viven en `../data/dags/` y `../data/dbt/` — separación deliberada infra/contenido (ver `ARCHITECTURE.md`).

## Fix aplicado sobre el template original (`vergissberlin/railwayapp-airflow`)

El template original crashea al montar un volumen de Railway porque:

1. El contenedor corre como usuario no-root `airflow` (uid 50000) por herencia de la imagen base.
2. Railway monta volúmenes nuevos con dueño `root`.
3. El entrypoint intenta escribir `simple_auth_manager_passwords.json.generated.tmp` en el volumen → `PermissionError: [Errno 13]`.

**Fix (en `infra/airflow/`):**
- `Dockerfile`: agregado `USER root` antes del `ENTRYPOINT`, para que el wrapper corra como root.
- `docker-entrypoint.sh`: agregado `chown -R "${AIRFLOW_UID:-50000}:0" /opt/airflow/data` después del `mkdir -p`, antes de que cualquier proceso intente escribir ahí.
- El `/entrypoint` oficial de la imagen base (invocado al final vía `exec /entrypoint airflow standalone`) sigue encargándose de bajar privilegios al usuario `airflow` para el proceso final — no se toca esa parte.

## Configuración del servicio en Railway (declarada en `.railway/railway.ts`)

| Campo | Valor |
|---|---|
| Builder | DOCKERFILE (`infra/airflow/Dockerfile`), build context raíz del repo |
| Dominio público | `airflow-production-2d51.up.railway.app` |
| Healthcheck | `/api/v2/monitor/health`, timeout 1800s |
| Volumen | `airflow-data`, 5000 MB, montado en `/opt/airflow/data` |
| Modo Airflow | `standalone` (SequentialExecutor, un solo proceso — apiserver+scheduler+DB en un contenedor) |
| Metadata DB | SQLite en el volumen (`/opt/airflow/data/airflow.db`) — suficiente para el volumen de este proyecto, no para producción real |

## Variables de entorno (nombres — valores nunca en el repo)

Declaradas en `.railway/railway.ts` con `preserve()` (mantienen el valor ya seteado en Railway, no se pisan desde el archivo):

| Variable | Origen | Propósito |
|---|---|---|
| `AIRFLOW_UID` | default del template (`50000`) | UID del usuario `airflow`, usado también por el `chown` del fix |
| `AIRFLOW__CORE__LOAD_EXAMPLES` | default del template (`False`) | No cargar los DAGs de ejemplo de Airflow |
| `_AIRFLOW_WWW_USER_USERNAME` | default del template (`admin`) | Usuario admin inicial |
| `_AIRFLOW_WWW_USER_PASSWORD` | **rotada manualmente** a un secreto generado — el default del template (`replace-with-strong-password`) queda inseguro si no se cambia | Password del admin, reescrita en cada boot por el entrypoint (login estable entre redeploys) |

## Cómo reproducir este despliegue desde cero

```bash
# 1. Clonar el repo del equipo
git clone https://github.com/diego-rejalas/factored-hackathon-2026-bitcoders.git
cd factored-hackathon-2026-bitcoders

# 2. Instalar el SDK de Railway IaC y vincular el proyecto
npm install railway
railway login
railway link

# 3. Previsualizar y aplicar la config declarada en .railway/railway.ts
railway config plan
railway config apply
```

## Pendiente / próximos pasos

- [x] DAG de ingesta implementado: bootstrap de la base `data` y sus schemas `bronze`/`silver`/`gold`, S3 → `bronze.*` → trigger dbt. Cada cambio de DAG dispara rebuild de la imagen de Airflow (aceptado a esta escala, ver `ARCHITECTURE.md`).
- [ ] SQLite alcanza para el hackathon; si se necesita concurrencia entre DAGs, migrar `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN` al Postgres ya provisto en el proyecto, documentado como camino de escalamiento, no implementado ahora.
