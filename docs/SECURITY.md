# Seguridad

*Los controles de la aplicación y los resultados del análisis de la infraestructura con Checkov y Trivy.*

[Índice](README.md) · [Arquitectura](ARCHITECTURE.md) · [API](API.md)

## Controles de la aplicación

| Control | Dónde |
|---|---|
| La identidad sale siempre de un JWT firmado con vencimiento y rol (`customer` o `admin`); el agente nunca acepta un `customer_id` dicho en el chat | backend y agente |
| Cada consulta se filtra por el cliente del token; un recurso ajeno devuelve 404, no 403, para no confirmar que existe | backend |
| La política (umbral, fraude, ambigüedad) es código determinista, no un prompt | `agent/app/guardrail.py` |
| El borrador de un modelo pasa por comprobaciones antes de enviarse | `agent/app/grounding.py` |
| `is_fraud` y `fraud_score` no existen en `gold` ni en ningún esquema de respuesta (lo comprueba una prueba del contrato) | backend |
| Contraseñas con bcrypt, bloqueo tras intentos fallidos y misma respuesta para usuario inexistente y clave errónea | backend |
| El backend es privado: solo cuentas de servicio con `run.invoker` lo llaman, con su ID token | infraestructura |
| Cada servicio tiene su cuenta de servicio, sus propios secretos y su propio rol en la base | infraestructura |
| Cloud Armor con reglas WAF y límite de tasa delante del frontend y del agente | infraestructura |
| Cloud SQL con IP privada y SSL obligatorio; la VM de Airflow sin IP externa, accesible por IAP | infraestructura |
| El despliegue desde GitHub usa federación de identidad, sin llaves guardadas | infraestructura |

El ingreso del chat sigue aceptando cliente más número de documento: es un sandbox y se presenta como tal, no como identidad real.

## Qué cubre cada herramienta

| | Checkov | Trivy |
|---|---|---|
| Terraform | Sí | Sí |
| Dockerfiles y workflows de GitHub Actions | Sí | Sí |
| Vulnerabilidades de las imágenes construidas | No | **Sí** |
| Dependencias de los archivos de bloqueo | No | Sí |
| Secretos en el repositorio | No | Sí |

## Qué se encontró y qué se hizo

| Hallazgo | Veredicto | Acción |
|---|---|---|
| Cloud SQL sin SSL obligatorio | Real | `ssl_mode = ENCRYPTED_ONLY` en los tres ambientes |
| Cloud SQL de `dev` con IP pública abierta a `0.0.0.0/0` | Real | `dev` pasa a IP privada, como qa y prod |
| Sin registro de conexiones, esperas, checkpoints ni DDL | Real | Opciones de auditoría activadas en los tres ambientes |
| Subred sin registro de flujo | Real | Muestreo del 50 % |
| Contenedor del ETL como `root` | Real | Usuario `etl` (uid 10001); el pipeline completo se probó como no root |
| Imagen de Airflow sin `USER` | Real, menor | `USER airflow` explícito |
| Workflows con permisos de escritura por defecto | Real | `permissions: contents: read` a nivel superior |
| Imagen de Airflow con 25 críticas y 208 altas | Real | Base `slim` y dependencias actualizadas: 17 críticas y 148 altas, de 2,81 GB a 1,34 GB |
| Llaves de S3 del organizador | Solo en el `.env` local, **no versionado** (se comprobó) | Ninguna: no hay secretos en el repositorio ni en las imágenes |

## Decisiones aceptadas, con su razón

Cada una está comentada en `.checkov.yaml` y `.trivyignore.yaml`.

- **Cifrado con claves de Google y no de cliente** (CKV_GCP_37, 38, 84): una clave suministrada por el cliente convierte una clave perdida en datos perdidos, y KMS agrega una dependencia que aquí no hace falta.
- **Rol de instancia para el agente de servicio de Compute** (CKV_GCP_42): lo necesita para apagar la VM de Airflow por horario. Es un agente de Google, no una cuenta de carga de trabajo.
- **Sin `log_hostname`, `log_duration` ni `pgaudit`**: el primero añade una consulta DNS por conexión, el segundo registra cada sentencia, y `pgaudit` no registra nada hasta crear la extensión.
- **Sin registro de acceso del bucket del lago**: pediría un segundo bucket solo para registros; los datos son sintéticos y el bucket es privado.
- **CKV_DOCKER_2 (HEALTHCHECK)**: Cloud Run ignora esa instrucción y usa sus propias sondas.

## Pendiente

- Los contenedores `backend`, `agent` y `frontend` corren como `root`: falta un `USER` no root en cada Dockerfile.
- Las imágenes base (Python sobre Debian 13.7 y Airflow sobre Debian 12.15) tienen 45 y 153 paquetes del sistema con vulnerabilidades altas **sin arreglo publicado**. Se resuelve con una imagen base más nueva cuando exista el parche.
- Auditoría real con `pgaudit` y registro de acceso del lago: no se hicieron.

## Por qué Terraform no se escanea desde el código fuente

Checkov y Trivy leen el HCL sin evaluarlo. No resuelven bloques `dynamic` ni condicionales sobre variables, así que dan como ausentes opciones que la configuración real sí fija (el modo SSL y los registros de Cloud SQL). Escanear el código fuente marcaba 8 reglas del módulo de Cloud SQL como fallidas en cada ambiente.

Por eso, en el CI Checkov revisa solo Dockerfiles y workflows, con una línea base (`.checkov.baseline`) de los hallazgos previos: los nuevos hacen fallar el CI y los conocidos no. El flujo de despliegue (`gcp-deploy.yml`) genera el plan, lo escanea con Checkov en modo `terraform_plan` y aplica **ese mismo plan**.

## Qué hace cumplir el CI

| Puerta | Falla cuando |
|---|---|
| Checkov sobre Dockerfiles y workflows | aparece un hallazgo **nuevo** |
| Trivy `config` | aparece un hallazgo HIGH o CRITICAL no listado en `.trivyignore.yaml` |
| Trivy `fs` | se versiona un secreto |
| Trivy `image` (Airflow y ETL) | hay una vulnerabilidad CRITICAL **con arreglo disponible**; las que no lo tienen no cuentan porque bloquearían todos los builds |
| Checkov sobre el plan en `gcp-deploy` | el plan resuelto incumple una regla no omitida |

## Repetirlo en local

```bash
# Dockerfiles y workflows (usa .checkov.yaml y .checkov.baseline)
uv venv /tmp/ck && uv pip install --python /tmp/ck/bin/python checkov && /tmp/ck/bin/checkov

# Trivy desde su imagen oficial
docker run --rm -v "$PWD:/src" aquasec/trivy:latest config /src --severity HIGH,CRITICAL --ignorefile /src/.trivyignore.yaml --skip-dirs /src/frontend/node_modules
docker run --rm -v "$PWD:/src" aquasec/trivy:latest fs /src --scanners secret --skip-files /src/.env
```

Dos trampas con Checkov: carga solo el `.checkov.yaml` del directorio actual, y con varios directorios en la configuración escribe una línea base en cada uno, por eso la configuración usa un único directorio.
