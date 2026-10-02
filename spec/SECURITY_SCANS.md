# Análisis de seguridad de la infraestructura: Checkov y Trivy

Fecha de la primera pasada: 2026-10-02. Herramientas: Checkov 3.3.22 y Trivy 0.75.0. Este documento dice qué encontraron, qué se corrigió, qué se acepta y por qué, y cómo se repite. Lo que el CI hace cumplir está en la sección 6.

## 1. Qué cubre cada herramienta

| | Checkov | Trivy |
|---|---|---|
| Configuración de Terraform | Sí | Sí (`config`) |
| Dockerfiles y workflows de GitHub Actions | Sí | Sí (`config`) |
| **Vulnerabilidades de las imágenes construidas** | No | **Sí** (`image`) |
| Dependencias de los archivos de bloqueo (`pnpm-lock.yaml`, etc.) | No | Sí (`fs`) |
| Secretos en el repositorio | No | Sí (`fs`) |

## 2. Resultado de la primera pasada y qué se hizo

### Terraform (Checkov: 17 hallazgos; Trivy: parte de los mismos)

| Hallazgo | Veredicto | Acción |
|---|---|---|
| Cloud SQL sin SSL obligatorio | Real | `ssl_mode = ENCRYPTED_ONLY` en los tres ambientes |
| Cloud SQL con IP pública | Real en **dev**: base abierta a `0.0.0.0/0` | `dev` pasa a IP privada, sin redes autorizadas, igual que qa y prod. El valor por defecto del módulo ya no expone la base |
| Sin registro de conexiones, desconexiones, esperas de bloqueo, checkpoints, archivos temporales ni sentencias DDL | Real | Opciones de base de datos activadas (`db_audit_logging`, encendido en los tres ambientes) |
| Subred sin registro de flujo | Real | `log_config` con muestreo del 50% |
| Discos y registro de imágenes sin claves de cliente (CSEK, CMEK) | Decisión | Se omite: ver sección 3 |
| `roles/compute.instanceAdmin.v1` para el agente de servicio de Compute | Decisión | Se omite: ver sección 3 |
| `log_hostname`, `log_duration`, `pgaudit` | Decisión | Se omiten: ver sección 3 |
| Bucket del lago sin registro de acceso | Decisión | Se omite: ver sección 3 |

### Dockerfiles y workflows

| Hallazgo | Veredicto | Acción |
|---|---|---|
| Contenedor del ETL como `root` | Real | Usuario `etl` (uid 10001) con las extensiones de DuckDB ya instaladas. Se probó el pipeline completo como no root |
| Imagen de Airflow sin `USER` explícito | Real (menor) | `USER airflow` explícito |
| Contenedores `backend`, `agent`, `frontend`, `infra/dbt` como `root` | Real, **no se tocó** | Código de otro equipo o heredado de Railway; está en la línea base (sección 5) |
| `infra/airflow` (Railway) como `root` | Intencional | Necesita ajustar el propietario del volumen montado; Railway es el stack anterior |
| Workflows con permisos de escritura por defecto | Real | `permissions: contents: read` a nivel superior en ambos |
| `workflow_dispatch` con entradas que llegan al build | Aceptado | Ver sección 3 |

### Vulnerabilidades de las imágenes (Trivy, solo HIGH y CRITICAL)

| Imagen | Antes | Después | Nota |
|---|---|---|---|
| **airflow** | 25 críticas, 208 altas, 92 con arreglo, 80 de paquetes de Python | 17 críticas, 148 altas, 24 con arreglo, 12 de paquetes de Python | Base `slim` (sin los ~100 proveedores opcionales: se quitan `litellm`, `snowflake`...) y actualización de `PyJWT`, `anyio`, `pyasn1`, `urllib3`, `sqlparse`. La imagen pasa de 2,81 GB a 1,34 GB |
| etl | 0 críticas, 45 altas | igual | Todas del sistema (Debian), 1 con arreglo |
| backend, agent | 0 críticas, 45 altas | igual | Mismo caso. No se tocaron |
| **frontend** | **2 críticas**, 22 altas, **24 de 24 con arreglo** | sin cambios | `next` 14.2.30; los arreglos están en 15.5.24 y 16.3.3. Código de otro equipo: **ver sección 4** |

Todos los paquetes vulnerables de Python de la imagen de Airflow venían de la imagen base oficial (se comprobó: mismas versiones en la base y en la construida). Lo que no se puede resolver aquí: los 153 paquetes del sistema de Debian 12 (perl, sqlite, libxml2, openssh, zlib), casi todos **sin arreglo publicado**, y `stdlib` de Go y `quinn-proto` de Rust, que están compilados dentro de binarios de la base. `cryptography` solo tiene arreglo en una versión mayor nueva y se dejó. Mitigación: la VM no tiene IP externa y solo admite entrada por IAP.

### Secretos
Trivy solo encontró las llaves de S3 del organizador en el `.env` **local**, que no está versionado en git (se comprobó). No hay secretos en el repositorio ni en ninguna imagen.

## 3. Decisiones y su razón (están en `.checkov.yaml`, cada una comentada)

- **Claves de cifrado de cliente (CKV_GCP_37, 38, 84):** se usan las claves que administra Google (AES-256). Las claves suministradas por el cliente convierten una clave perdida en datos perdidos, y las administradas con KMS agregan una dependencia que aquí no hace falta.
- **CKV_GCP_42:** el agente de servicio de Compute Engine necesita ese rol para apagar la VM de Airflow por horario. Es un agente de Google, no una cuenta de usuario o de carga de trabajo.
- **CKV_GCP_108 y CKV2_GCP_13:** `log_hostname` hace una consulta DNS inversa por conexión (latencia) y `log_duration` registra cada sentencia (volumen y costo). **CKV_GCP_110:** `pgaudit` no registra nada hasta que también se crea la extensión en la base.
- **CKV_GCP_62 y CKV_GCP_63:** registrar el acceso del bucket pide un segundo bucket solo para registros; los datos son sintéticos y el bucket es privado (prevención de acceso público forzada).
- **CKV_GCP_6:** la base exige SSL con `ssl_mode`, visible en el plan resuelto. Checkov solo reconoce el atributo antiguo `require_ssl`, que el proveedor dejó obsoleto.
- **CKV_GHA_7:** la entrada de `workflow_dispatch` llega al build solo como nombre de ambiente, restringido a `dev`, `qa` y `prod`, y solo quien tiene permiso de escritura puede lanzarlo.
- **CKV_DOCKER_2 (HEALTHCHECK):** Cloud Run ignora esa instrucción y usa sus propias sondas; los contenedores de Airflow tienen la suya en el archivo de compose.

## 4. Pendiente y lo que no se hizo

- **Frontend: `next` 14.2.30 con 2 vulnerabilidades críticas y 12 altas, todas con arreglo.** Es el frontend de otro integrante y se acordó dejarlo como está. Subir `next` a 15.5.24 o superior las resuelve; es una decisión del dueño del código.
- Contenedores `backend`, `agent` y `frontend` como `root`: un `USER` no root en cada Dockerfile.
- La imagen base de Python (Debian 13.7) y la de Airflow (Debian 12.15) tienen 45 y 153 paquetes del sistema con vulnerabilidades altas sin arreglo publicado: se resuelve con una imagen base más nueva cuando exista el parche.
- Auditoría real con `pgaudit` (requiere crear la extensión) y registro de acceso del lago: no se hicieron.

## 5. Por qué Terraform no se escanea desde el código fuente

Checkov y Trivy leen el HCL sin evaluarlo. No resuelven bloques `dynamic` ni condicionales sobre variables, así que dan como ausentes opciones que la configuración real sí fija (las opciones de registro y el modo SSL de Cloud SQL). Comprobado: escanear el código fuente marcaba 8 reglas del módulo de Cloud SQL como fallidas en cada ambiente, y el **plan resuelto** de prod (`terraform show -json`) pasa **54 comprobaciones y falla 0** con las omisiones de la sección 3.

Por eso:
- Checkov **no** escanea Terraform en el CI de código: solo Dockerfiles y workflows (`.checkov.yaml`), con una línea base (`.checkov.baseline`) de los hallazgos que ya existían en código ajeno: los nuevos hacen fallar el CI, los conocidos no.
- El workflow de despliegue (`gcp-deploy.yml`) genera el plan, lo escanea con Checkov en modo `terraform_plan` y aplica **ese mismo plan**.
- Trivy `config` sí se ejecuta sobre el repositorio, con `.trivyignore.yaml`, donde cada omisión lleva su razón.

## 6. Qué hace cumplir el CI

| Job | Falla cuando |
|---|---|
| `security` → Checkov | aparece un hallazgo **nuevo** en Dockerfiles o workflows (los de `.checkov.baseline` no cuentan) |
| `security` → Trivy `config` | aparece un hallazgo HIGH o CRITICAL no listado en `.trivyignore.yaml` |
| `security` → Trivy `fs` | se versiona un secreto |
| `pipeline` → Trivy `image` (Airflow y ETL) | hay una vulnerabilidad **CRITICAL con arreglo disponible**. Las que no tienen arreglo no cuentan: no se pueden resolver y bloquearían todos los builds |
| `gcp-deploy` → Checkov sobre el plan | el plan resuelto incumple una regla no omitida |

Se probó que cada puerta **pasa con el repositorio actual y falla ante un hallazgo nuevo**.

## 7. Repetirlo en local

```bash
# Dockerfiles y workflows (usa .checkov.yaml y .checkov.baseline)
uv venv /tmp/ck && uv pip install --python /tmp/ck/bin/python checkov && /tmp/ck/bin/checkov

# Terraform, sobre el plan resuelto (hay que correrlo desde un directorio sin .checkov.yaml)
cd infra/gcp/envs/prod && terraform plan -out=/tmp/plan.bin <variables> && terraform show -json /tmp/plan.bin > /tmp/plan.json
cd /tmp && /tmp/ck/bin/checkov -f plan.json --framework terraform_plan --skip-check "<los de .checkov.yaml>"

# Trivy desde su imagen oficial
docker run --rm -v "$PWD:/src" aquasec/trivy:latest config /src --severity HIGH,CRITICAL --ignorefile /src/.trivyignore.yaml --skip-dirs /src/frontend/node_modules
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest image <imagen> --severity HIGH,CRITICAL
docker run --rm -v "$PWD:/src" aquasec/trivy:latest fs /src --scanners secret --skip-files /src/.env   # el .env local tiene las llaves de S3 y no está en git
```

Dos trampas al ejecutar Checkov: carga solo el `.checkov.yaml` del directorio actual, y con varios directorios en la configuración escribe una línea base en cada uno (por eso la configuración usa un único directorio).
