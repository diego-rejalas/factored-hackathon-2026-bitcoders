# infra/gcp/ — infraestructura en GCP por ambientes

Terraform de GCP separado en **tres ambientes** (`dev`, `qa`, `prod`) que comparten módulos. Cada ambiente tiene su propio estado, sus propios recursos (todos con el prefijo `factored-<ambiente>`) y valores por defecto adecuados a su rol.

```text
infra/gcp/
├── envs/
│   ├── dev/    backend.tf provider.tf main.tf variables.tf outputs.tf terraform.tfvars.example
│   ├── qa/     (mismo contenido; cambian los valores por defecto de variables.tf)
│   └── prod/
├── modules/
│   ├── foundation/         APIs del proyecto + Artifact Registry
│   ├── network/            VPC, subred, Private Service Access, firewall de IAP y NAT opcional
│   ├── cloudsql/           Cloud SQL Postgres 16 (base `data`, usuario `app`)
│   ├── secrets/            Secret Manager: JWT, contraseña de la base, claves de LLM y de S3
│   ├── lakehouse/          bucket de GCS para el Parquet de bronze y silver
│   ├── cloud_run_service/  un servicio de Cloud Run con su propia cuenta de servicio
│   └── etl_job/            el Cloud Run Job del ETL
├── scripts/                setup-backend.sh · manage_db.sh · grant_access.sh · smoke.py
├── docs/                   TEAM_ONBOARDING.md
└── etl/                    Dockerfile y run_pipeline.py de la imagen del job
```

`main.tf` es idéntico en los tres ambientes (así no divergen); lo que cambia es `backend.tf` (prefijo del estado) y los valores por defecto de `variables.tf`.

## Qué despliega cada ambiente

`foundation` → `network` → `cloudsql`, `secrets`, `lakehouse` → servicios `backend`, `agent`, `frontend` y el job `etl`. Un `plan` real contra el proyecto da **54 recursos en cada ambiente** (7 son la red y dos APIs).

| | dev | qa | prod |
|---|---|---|---|
| Cloud SQL | `db-f1-micro`, 20 GB | `db-g1-small`, 20 GB | `db-custom-2-7680`, 50 GB, recuperación a un instante |
| Conectividad a la base (`db_connectivity`) | `public_ip`: IP pública abierta (`0.0.0.0/0`), como el stack original | `private_ip`: sin IP pública, por la VPC | `private_ip`: sin IP pública, por la VPC |
| Rangos de red | `10.10.0.0/24` y `10.10.1.0/24` | `10.20.0.0/24` y `10.20.1.0/24` | `10.30.0.0/24` y `10.30.1.0/24` |
| Protección contra borrado (base y Cloud Run) | no | no | **sí** |
| Instancias mínimas (backend, agent) | 0 | 0 | 1 |
| Bucket del lago | se puede destruir con datos | se puede destruir con datos | **no** |

Las diferencias salen de variables (`db_tier`, `use_cloud_sql_connector`, `db_deletion_protection`, `agent_min_instances`, ...): se pueden cambiar en un `terraform.tfvars` sin tocar el código.

## Mejoras respecto al Terraform plano anterior

- **Cada servicio tiene su propia cuenta de servicio** y puede leer solo los secretos que se le asignan. Antes los tres usaban la cuenta de cómputo por defecto, con acceso a todos los secretos del proyecto.
- **La contraseña de la base va en Secret Manager** y se monta como variable de entorno. Antes se escribía en claro en la definición de cada servicio.
- **Red propia por ambiente** (`modules/network`): una VPC, una subred de aplicación con Private Google Access, y Private Service Access para que Cloud SQL tenga IP privada. En qa y prod la base **no tiene dirección pública**.
- **Tres modos de llegar a la base** (`db_connectivity`): `public_ip` (lo del stack original), `connector` (Cloud SQL connector por socket, sin lista de redes; las apps leen `PG_HOST` como host de libpq o asyncpg y ambos aceptan un directorio de socket) y `private_ip`. Se cambia con una variable.
- **Cloud Run usa Direct VPC egress** con `PRIVATE_RANGES_ONLY`: solo el tráfico hacia rangos privados pasa por la VPC; el resto sale a internet normal, así que **no hace falta Cloud NAT** para el ETL (S3) ni para el agente (OpenRouter).
- **Estado separado por ambiente** (`env/<ambiente>`, en `bitcoders-factored-hackathon-tfstate`) y bloqueo de GCS por defecto.
- Las llaves de S3 del organizador se cargan a mano como una versión nueva del secreto; un `apply` posterior no la revierte.
- Bucket del lago con versionado y acceso público prohibido.
- Se quitó el permiso `run.invoker` de la cuenta del ETL sobre su propio job: no cumplía ninguna función.
- Región por defecto `us-east4` (la más cercana a `us-east-2`, donde está el bucket del organizador), en lugar de `us-central1`.

## Prerequisitos (una vez por proyecto)

1. Proyecto de GCP con facturación, y `gcloud` y `terraform >= 1.6` instalados. Autenticarte: `gcloud auth login && gcloud config set project <PROJECT_ID>`.
2. Crear el bucket de estado (compartido por los tres ambientes):
   ```bash
   PROJECT_ID=<PROJECT_ID> ./infra/gcp/scripts/setup-backend.sh
   ```
3. Para el despliegue por CI: secreto de repositorio `GCP_SA_KEY` y variables `GCP_PROJECT_ID`, `GCP_STATE_BUCKET` (y opcionalmente `GCP_REGION`). Ver `.github/workflows/gcp-deploy.yml`.

## Desplegar un ambiente a mano

```bash
cd infra/gcp/envs/dev                      # o qa, prod
cp terraform.tfvars.example terraform.tfvars   # editar project_id y, si quieres, las claves
terraform init        # el bucket y el prefijo ya están en backend.tf

# 1. APIs y registro de imágenes
terraform apply -target=module.foundation

# 2. Construir y subir las imágenes (desde la raíz del repo)
REG=us-east4-docker.pkg.dev/<PROJECT_ID>/factored-dev
gcloud auth configure-docker us-east4-docker.pkg.dev
for s in backend agent frontend; do docker build . -f $s/Dockerfile -t $REG/$s:latest && docker push $REG/$s:latest; done
docker build . -f infra/gcp/etl/Dockerfile -t $REG/etl:latest && docker push $REG/etl:latest

# 3. El resto
terraform apply
```

Después del primer `apply`, copiar las llaves de S3 del organizador al Secret Manager (nunca a git ni a variables de Terraform):

```bash
printf '%s' "$LATAM_BANK_AWS_ACCESS_KEY_ID"     | gcloud secrets versions add factored-dev-latam-bank-aws-id     --data-file=-
printf '%s' "$LATAM_BANK_AWS_SECRET_ACCESS_KEY" | gcloud secrets versions add factored-dev-latam-bank-aws-secret --data-file=-
```

Ejecutar el ETL: `gcloud run jobs execute factored-dev-etl --region us-east4 --wait`.

## Por CI

`.github/workflows/gcp-deploy.yml`: un `push` a `main` hace el build de las imágenes y un `plan` de **dev**. Con `workflow_dispatch` se elige el ambiente (`dev`, `qa`, `prod`) y `plan` o `apply`, y opcionalmente se ejecuta el ETL. Como el job usa `environment:` de GitHub, se puede exigir una aprobación manual para `prod` desde la configuración del repositorio.

## Ahorro de costos

```bash
ENVIRONMENT=dev ./infra/gcp/scripts/manage_db.sh pause    # la base deja de cobrar cómputo
ENVIRONMENT=dev ./infra/gcp/scripts/manage_db.sh resume   # vuelve en ~60 s con los datos
ENVIRONMENT=dev ./infra/gcp/scripts/manage_db.sh status
```

Cloud Run a 0 instancias cuesta casi nada; Cloud SQL es el único costo permanente.

## Estado de esta estructura y qué falta

**Verificado:** `terraform fmt`, `init` y `validate` pasan en los tres ambientes, y un `plan` real contra `bitcoders-factored-hackathon` los planifica sin errores ni choques con el stack anterior.
**No verificado:** ningún `apply` contra GCP. En particular la ruta privada de qa y prod (Private Service Access, Direct VPC egress de Cloud Run, y que el ETL de DuckDB conecte a la IP privada) está sin probar, y el modo `connector` también. `dev` es el ambiente que reproduce lo que ya funcionaba.

Pendiente de endurecer (no cambió con esta reestructura):
- Backend y agente siguen abiertos a todos (`allUsers`): el agente llama al backend sin token de identidad. Cerrar el backend exige que el agente envíe un ID token.
- La base sigue con usuario `app` único (propietario). Falta separar un rol de solo lectura para `gold` y otro acotado a `app.*` y `agent.trace_log`.
- `ssl_mode=ENCRYPTED_ONLY`, presupuesto con alerta y monitoreo.
- **Acceso humano a una base privada:** desde un portátil no se llega a una instancia sin IP pública (ni con `cloud-sql-proxy`, que debe estar dentro de la VPC). El camino previsto es entrar por IAP a la VM de Airflow (el firewall de `modules/network` ya permite el rango de IAP para instancias con la etiqueta `iap`) y conectar desde ahí. Mientras no exista esa VM, `dev` (IP pública) es el ambiente para consultas manuales.
- El CI usa una llave JSON de larga vida; mejor Workload Identity Federation.
- **Airflow y dbt como servicio no están en este Terraform** (el pipeline es el Cloud Run Job con `dbt-duckdb`). Llevarlos a GCP es el siguiente paso, y encaja como un módulo nuevo `airflow` (VM de Compute Engine) en los tres ambientes.

## Migración desde el stack anterior

El stack desplegado antes de esta separación usa nombres antiguos (`factored-hackathon`, `us-central1`) y estado sin prefijo de ambiente. Los ambientes nuevos son despliegues **nuevos** (otros nombres, otra región): no reemplazan al anterior ni lo destruyen. Para retirarlo, hacer `terraform destroy` con la versión anterior del código (commit `62a97b1`) y su estado, después de verificar el ambiente nuevo.
