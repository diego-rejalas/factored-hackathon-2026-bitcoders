# Despliegue de Airflow — mapeo completo

Estado real en Railway (proyecto `factored-hackathon`, servicio `railwayapp-airflow`), documentado siguiendo la convención de "Railway como código" de `ARCHITECTURE.md`.

## Fuente

- Repo: `diego-rejalas/railwayapp-airflow-private` (privado, fork fixeado de `vergissberlin/railwayapp-airflow`).
- Rama: `main`.
- Build: Dockerfile propio (`apache/airflow:3.3.0-python3.12` + `requirements.txt` + entrypoint custom).

## Fix aplicado sobre el template original

El template original crashea al montar un volumen de Railway porque:

1. El contenedor corre como usuario no-root `airflow` (uid 50000) por herencia de la imagen base.
2. Railway monta volúmenes nuevos con dueño `root`.
3. El entrypoint intenta escribir `simple_auth_manager_passwords.json.generated.tmp` en el volumen → `PermissionError: [Errno 13]`.

**Fix (en el fork):**
- `Dockerfile`: agregado `USER root` antes del `ENTRYPOINT`, para que el wrapper corra como root.
- `docker-entrypoint.sh`: agregado `chown -R "${AIRFLOW_UID:-50000}:0" /opt/airflow/data` después del `mkdir -p`, antes de que cualquier proceso intente escribir ahí.
- El `/entrypoint` oficial de la imagen base (invocado al final vía `exec /entrypoint airflow standalone`) sigue encargándose de bajar privilegios al usuario `airflow` para el proceso final — no se toca esa parte.

## Configuración del servicio en Railway

| Campo | Valor |
|---|---|
| Builder | RAILPACK (Dockerfile) |
| Dominio público | `railwayapp-airflow-production-fd99.up.railway.app` |
| Volumen | `airflow-data`, 5000 MB, montado en `/opt/airflow/data` |
| Modo Airflow | `standalone` (SequentialExecutor, un solo proceso — apiserver+scheduler+DB en un contenedor) |
| Metadata DB | SQLite en el volumen (`/opt/airflow/data/airflow.db`) — suficiente para el volumen de este proyecto, no para producción real |

## Variables de entorno (nombres — valores nunca en el repo)

| Variable | Origen | Propósito |
|---|---|---|
| `AIRFLOW_UID` | default del template (`50000`) | UID del usuario `airflow`, usado también por el `chown` del fix |
| `AIRFLOW__CORE__LOAD_EXAMPLES` | default del template (`False`) | No cargar los DAGs de ejemplo de Airflow |
| `_AIRFLOW_WWW_USER_USERNAME` | default del template (`admin`) | Usuario admin inicial |
| `_AIRFLOW_WWW_USER_PASSWORD` | **rotada manualmente** a un secreto generado (`${{secret(32)}}`) — el default del template (`replace-with-strong-password`) queda inseguro si no se cambia | Password del admin, reescrita en cada boot por el entrypoint (login estable entre redeploys) |

## Cómo reproducir este despliegue desde cero

```bash
# 1. Clonar el fork con el fix
git clone https://github.com/diego-rejalas/railwayapp-airflow-private.git

# 2. En Railway: crear servicio nuevo apuntando a ese repo, rama main
# 3. Adjuntar volumen en /opt/airflow/data (mínimo 1-5 GB)
# 4. Setear _AIRFLOW_WWW_USER_PASSWORD a un secreto propio (no dejar el default)
# 5. Generar dominio público del servicio
```

## Pendiente / próximos pasos

- [ ] Escribir el DAG real de ingesta (S3 → `raw.*` → trigger dbt) en `dags/` del repo del equipo (no en este fork del template) y apuntar `AIRFLOW_DAGS_GIT_REPO_URL` o montar el DAG directamente en el fork — a decidir cuando se defina el workflow ganador.
- [ ] SQLite alcanza para el hackathon; si se necesita concurrencia entre DAGs, migrar `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN` al Postgres ya provisto en el proyecto (`Postgres`, sin usar), documentado como camino de escalamiento, no implementado ahora.
