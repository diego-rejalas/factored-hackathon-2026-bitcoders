# Onboarding del equipo: acceso a GCP y a los datos

[Índice](README.md) · [Arquitectura](ARCHITECTURE.md) · [Despliegue](DEPLOY.md)

> **Proyecto:** `bitcoders-factored-hackathon` · **Región:** `us-east4` · **Ambiente:** `prod` (`dev` y `qa` usan el mismo esquema de nombres: `factored-<ambiente>`).
>
> Los scripts de `infra/gcp/scripts/` toman `ENVIRONMENT=dev|qa|prod` (por defecto `dev`). Para `prod`, anteponlo: `ENVIRONMENT=prod ./infra/gcp/scripts/...`.

Cómo autenticarte y llegar a la base de datos PostgreSQL, al lakehouse en Cloud Storage y a los servicios de Cloud Run. Quien da los accesos es el dueño del proyecto (`infra/gcp/scripts/grant_access.sh`).

---

## 1. Prerrequisitos en tu Computadora

Instala las siguientes herramientas básicas (si aún no las tienes):
1. **Google Cloud CLI (`gcloud`):** [Instrucciones de instalación](https://cloud.google.com/sdk/docs/install).
2. **Cliente de Base de Datos:** [DBeaver](https://dbeaver.io/) (recomendado), DataGrip, pgAdmin o `psql`.
3. **Cloud SQL Auth Proxy** (solo para `dev`; en `prod` la base es privada):
   * **macOS (Homebrew):** `brew install cloud-sql-proxy`
   * **Linux:**
     ```bash
     curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.14.0/cloud-sql-proxy.linux.amd64
     chmod +x cloud-sql-proxy
     sudo mv cloud-sql-proxy /usr/local/bin/
     ```
   * **Windows:** Descargar el ejecutable desde [Google Cloud SQL Proxy](https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.14.0/cloud-sql-proxy.x64.exe).

---


## 2. Autenticación en Google Cloud

Abre tu terminal y autentícate con la cuenta de Google (Gmail) a la que se le dio acceso:

```bash
# 1. Iniciar sesión en GCP
gcloud auth login

# 2. Habilitar credenciales de aplicación local (necesario para consultar el Lakehouse y Storage)
gcloud auth application-default login

# 3. Fijar el proyecto activo
gcloud config set project bitcoders-factored-hackathon
```

---

## 3. La base de datos (`data`)

En `prod` Cloud SQL tiene **solo IP privada**: no hay IP pública ni lista de redes autorizadas, así que el Auth Proxy desde tu computadora **no llega**. Se entra por la VM de Airflow, que está dentro de la red y a la que se llega por IAP (sin IP externa).

```bash
# 1. Enciende la VM (se apaga sola a las 03:00) y espera ~1 minuto
ENVIRONMENT=prod ./infra/gcp/scripts/airflow_vm.sh start

# 2. Una consulta desde el contenedor del scheduler, que ya tiene las credenciales del pipeline
gcloud compute ssh factored-prod-airflow --zone us-east4-a --project bitcoders-factored-hackathon \
    --tunnel-through-iap --command "sudo docker exec airflow-scheduler-1 python -c \"import os,psycopg2; c=psycopg2.connect(host=os.environ['PG_HOST'],dbname=os.environ['PG_DATABASE'],user=os.environ['PG_USER'],password=os.environ['PG_PASSWORD'],sslmode='require'); cur=c.cursor(); cur.execute('select count(*) from gold.transactions'); print(cur.fetchone())\""

# 3. Al terminar
ENVIRONMENT=prod ./infra/gcp/scripts/airflow_vm.sh stop
```

Esa cuenta es la del pipeline (escribe `gold`): úsala solo para consultar. Un cliente gráfico (DBeaver, DataGrip) no llega a la base en `prod`; para explorar datos sin tocar la VM, usa el lakehouse (apartado 4).

Si el dueño del proyecto te dio acceso a `dev`, esa base y sus scripts (`manage_db.sh`) siguen su propia configuración: pregúntale cómo se entra.

#### Esquemas
* `gold.*`: tablas de negocio para el servicio (`customers`, `products`, `transactions`, `complaints`, `call_center_interactions`).
* `ops.etl_runs`: historial de corridas del pipeline.
* `agent.trace_log` y `agent.conversation_messages`: traza del agente (sin texto del cliente) e historial de conversaciones.
* `app.*`: casos de disputa y sus eventos.

---

## 4. El lakehouse (Cloud Storage, Parquet)

**Bronze** (datos crudos) y **Silver** (estandarizados y tipados) están en Parquet con compresión ZSTD en `gs://factored-prod-lakehouse-bitcoders-factored-hackathon` (`bronze/<tabla>/`, `silver/<tabla>/` y `docs/`). No necesita la VM ni la base: lo lees desde tu máquina con DuckDB.

```python
import duckdb

con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs;")
con.execute("CREATE SECRET (TYPE GCS, PROVIDER CREDENTIAL_CHAIN);")

bucket = "gs://factored-prod-lakehouse-bitcoders-factored-hackathon"
print(con.execute(f"SELECT * FROM '{bucket}/silver/customers/customers.parquet' LIMIT 5").df())
print(con.execute(f"SELECT * FROM read_parquet('{bucket}/silver/transactions/**/*.parquet') LIMIT 5").df())
```

---

## 5. Los servicios (Cloud Run)

La interfaz y el agente salen por el balanceador (Cloud Armor delante); el backend es **privado** (solo el agente lo llama, con su identidad).

```bash
cd infra/gcp/envs/prod && terraform output edge_url      # https://<dominio>/  y  /agent/*
gcloud beta run services logs tail factored-prod-agent --region us-east4 --project bitcoders-factored-hackathon
gcloud beta run services logs tail factored-prod-backend --region us-east4 --project bitcoders-factored-hackathon
```

| Servicio | Cómo se llega | Qué es |
|---|---|---|
| `factored-prod-frontend` | `/` del balanceador | Chat del cliente y consola `/admin` |
| `factored-prod-agent` | `/agent/*` del balanceador (`POST /agent/chat`) | Agente y guardrail |
| `factored-prod-backend` | Privado (token de identidad) | API de herramientas bancarias |

---

## 6. Preguntas Frecuentes y Solución de Problemas

* **Error: `connection refused` o timeout al conectar a PostgreSQL:**
  * En `dev`, asegúrate de que el Cloud SQL Proxy esté corriendo en una terminal.
  * En `dev`, mira si la base está hibernada (`./infra/gcp/scripts/manage_db.sh status`; si está en `NEVER`, `resume`). En `prod` no se llega con el proxy: ver el apartado 3.
* **Error: `password authentication failed for user`:**
  * Revisa que estés ingresando el usuario y contraseña exactos que te proporcionaron en el aprovisionamiento.
* **Error: `Bucket not found` al consultar en GCS:**
  * Verifica haber ejecutado `gcloud auth application-default login` para que DuckDB y librerías cliente tomen tus credenciales locales.
