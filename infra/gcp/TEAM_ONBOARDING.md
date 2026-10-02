# Guía de Conexión y Onboarding para el Equipo (GCP & Datos)
> **Proyecto:** `bitcoders-factored-hackathon` | **Región:** `us-central1`  
> **Hackathon:** Factored AI & Data Hackathon 2026

Bienvenido al entorno de desarrollo en Google Cloud Platform (GCP). Esta guía te explica paso a paso cómo autenticarte y conectarte a la base de datos PostgreSQL, al Data Lakehouse en Cloud Storage y a los servicios en Cloud Run.

---

## 1. Prerrequisitos en tu Computadora

Instala las siguientes herramientas básicas (si aún no las tienes):
1. **Google Cloud CLI (`gcloud`):** [Instrucciones de instalación](https://cloud.google.com/sdk/docs/install).
2. **Cliente de Base de Datos:** [DBeaver](https://dbeaver.io/) (recomendado), DataGrip, pgAdmin o `psql`.
3. **Cloud SQL Auth Proxy (Recomendado para conectar sin abrir IPs):**
   * **macOS (Homebrew):** `brew install cloud-sql-proxy`
   * **Linux:**
     ```bash
     curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.14.0/cloud-sql-proxy.linux.amd64
     chmod +x cloud-sql-proxy
     sudo mv cloud-sql-proxy /usr/local/bin/
     ```
   * **Windows:** Descargar el ejecutable desde [Google Cloud SQL Proxy](https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.14.0/cloud-sql-proxy.x64.exe).

---

## 2. Paso 1: Autenticación en Google Cloud

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

## 3. Paso 2: Verificar o Reanudar la Base de Datos

Para minimizar costos, Cloud SQL utiliza **Hibernación Just-in-Time**. Si la base de datos estuvo en reposo, debes reanudarla antes de conectarte:

```bash
# Comprobar estado:
./infra/gcp/manage_db.sh status

# Si activationPolicy está en NEVER, reactívala (tarda ~60 segundos):
./infra/gcp/manage_db.sh resume
```

---

## 4. Paso 3: Conexión a Cloud SQL PostgreSQL (`data`)

### Método Recomendado: Cloud SQL Auth Proxy

El Proxy crea un túnel cifrado local seguro directamente con la instancia sin necesidad de configurar redes públicas.

1. **Inicia el proxy en una pestaña de tu terminal:**
   ```bash
   cloud-sql-proxy bitcoders-factored-hackathon:us-central1:factored-hackathon
   ```
   *Verás un mensaje indicando que el proxy está escuchando en `127.0.0.1:5432`.*

2. **Configura tu cliente de base de datos (DBeaver / DataGrip / psql):**
   * **Host:** `127.0.0.1` o `localhost`
   * **Puerto:** `5432`
   * **Database:** `data`
   * **Usuario:** Tu usuario asignado (ej. `tu_nombre` o `postgres`)
   * **Contraseña:** Tu contraseña asignada

#### Ejemplo de conexión rápida con `psql`:
```bash
psql "host=127.0.0.1 port=5432 dbname=data user=TU_USUARIO"
```

#### Esquemas disponibles en la base de datos:
* `gold.*` ➔ Tablas de negocio limpias y optimizadas para servicio (`customers`, `products`, `transactions`, `complaints`, etc.).
* `ops.etl_runs` ➔ Historial de corridas de ETL con métricas y resultados de calidad.
* `agent.trace_log` ➔ Logs de auditoría de cada paso del agente conversacional.

---

## 5. Paso 4: Consulta al Data Lakehouse (GCS Parquet)

Las capas **Bronze** (datos crudos) y **Silver** (datos estandarizados y tipados) están preservadas en formato columnar **Parquet con compresión ZSTD** en el bucket de Google Cloud Storage:
`gs://factored-lakehouse-bitcoders-factored-hackathon`

Puedes consultarlas directamente desde tu máquina con **DuckDB en Python** sin descargar gigabytes de archivos:

```python
import duckdb

con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs;")
con.execute("CREATE SECRET (TYPE GCS, PROVIDER CREDENTIAL_CHAIN);")

# Consultar capa Silver (Clientes activos)
df_customers = con.execute("""
    SELECT * 
    FROM 'gs://factored-lakehouse-bitcoders-factored-hackathon/silver/customers/customers.parquet'
    LIMIT 5
""").df()
print(df_customers)

# Consultar transacciones con particionado tipo Hive
df_tx = con.execute("""
    SELECT transaction_id, customer_id, amount, year, month, day
    FROM read_parquet('gs://factored-lakehouse-bitcoders-factored-hackathon/silver/transactions/*/*/*/*.parquet', hive_partitioning=true)
    WHERE amount > 500
    LIMIT 10
""").df()
print(df_tx)
```

---

## 6. Paso 5: Microservicios en la Nube (Cloud Run)

Los servicios de backend, agente y frontend están desplegados en Cloud Run:

| Servicio | URL Pública / Endpoint | Propósito |
| :--- | :--- | :--- |
| **Frontend Chat** | `https://frontend-127503393524.us-central1.run.app` | Interfaz web de usuario para simulación de chat. |
| **Agente AI (LangGraph)** | `https://agent-127503393524.us-central1.run.app` | Orquestador conversacional y guardrails (`POST /chat`). |
| **Backend Bancario** | `https://backend-127503393524.us-central1.run.app` | API de herramientas bancarias con OpenAPI docs en `/docs`. |

Para ver logs de ejecución en tiempo real desde tu consola:
```bash
gcloud beta run services logs tail agent --region=us-central1
gcloud beta run services logs tail backend --region=us-central1
```

---

## 7. Preguntas Frecuentes y Solución de Problemas

* **Error: `connection refused` o timeout al conectar a PostgreSQL:**
  * Asegúrate de que el Cloud SQL Proxy esté corriendo en una terminal.
  * Verifica si la base de datos está hibernada (`./infra/gcp/manage_db.sh status`). Si está en `NEVER`, ejecuta `./infra/gcp/manage_db.sh resume`.
* **Error: `password authentication failed for user`:**
  * Revisa que estés ingresando el usuario y contraseña exactos que te proporcionaron en el aprovisionamiento.
* **Error: `Bucket not found` al consultar en GCS:**
  * Verifica haber ejecutado `gcloud auth application-default login` para que DuckDB y librerías cliente tomen tus credenciales locales.
