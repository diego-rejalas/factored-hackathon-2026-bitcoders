# Evaluación de Arquitectura Empresarial, Viabilidad Real y Escalabilidad de Costos (TCO)

## 1. Resumen Ejecutivo y Veredicto Arquitectónico (BLUF)

La arquitectura implementada en este repositorio (**DuckDB efímero en Cloud Run Job + GCS Parquet Lakehouse + Cloud SQL PostgreSQL + FastAPI Banking Layer + LangGraph Agent**) es **100% viable, robusta y altamente eficiente para una FinTech, Neobanco o entidad financiera en etapas tempranas a medianas (Seed hasta Serie C, con volúmenes de hasta ~500.000 clientes activos)**. Logra un aislamiento estricto de seguridad (*zero-trust* entre el LLM y la base de datos), calidad de datos verificada antes de producción (*shift-left testing* con dbt) y un costo operativo extremadamente bajo (**TCO < $40 USD/mes**).

Sin embargo, para un **Banco Corporativo Tier-1 (millones de clientes, transacciones concurrentes 24/7 y auditoría regulatoria estricta como PCI-DSS, SOX y Basilea III)**, la arquitectura actual presenta **tech ceilings (límites duros de escalabilidad)** que exigen una evolución planificada:
1. **Límite de cómputo mononodo:** DuckDB reside en un único contenedor efímero (máximo 32 GB de RAM en Cloud Run); no escala horizontalmente para procesar cientos de millones de eventos diarios en clústeres distribuidos.
2. **Ausencia de transacciones ACID en el Lakehouse:** El almacenamiento en archivos Parquet planos carece de control de concurrencia, mutaciones transaccionales y viajes en el tiempo (*time-travel*), requiriendo formatos abiertos de tabla como **Apache Iceberg**.
3. **Ingesta Batch completa (*Full Re-scan*):** Re-leer todo el histórico de S3 es inviable frente a petabytes de datos; se requiere ingesta continua por **CDC (Change Data Capture)** vía Kafka/Debezium.
4. **Gobernanza y Privacidad (PII):** Los datos personales (`document_number`, nombres) se almacenan sin enmascaramiento dinámico a nivel de lago, lo cual incumple las normativas de protección de datos bancarios sin una capa como **Google Cloud Dataplex**.

---

## 2. Diagrama de Madurez y Evolución Arquitectónica

```text
┌────────────────────────────────────────────────────────────────┐
│   FASE 1: ARQUITECTURA ACTUAL (FinTech / Neobanco Ágil)        │
│   • Capacidad: < 50M filas (~100k usuarios activos)            │
│   • TCO: ~$25 - $45 USD/mes | Mantenimiento: 1 DevOps / Data   │
├────────────────────────────────────────────────────────────────┤
│  AWS S3 ──► DuckDB (RAM Cloud Run) ──► GCS Parquet (Lakehouse) │
│                    │                                           │
│                    ▼ (dbt build: 121 tests)                    │
│             Cloud SQL Postgres (Solo Gold de servicio)         │
│                    ▲                                           │
│             FastAPI (Tool Layer & Session) ◄── Agent LangGraph │
└───────────────────────────────┬────────────────────────────────┘
                                │
                                │ Requiere escalar a >50M filas,
                                │ ingesta delta y soporte ACID
                                ▼
┌────────────────────────────────────────────────────────────────┐
│   FASE 2: SCALE-UP (Banco Digital Mediano / 100k - 1M Usuarios) │
│   • Capacidad: 50M - 500M filas                                │
│   • TCO: ~$450 - $1,200 USD/mes                                │
├────────────────────────────────────────────────────────────────┤
│  Lakehouse ACID + Ingesta Incremental dbt                      │
│  • GCS Data Lakehouse gestionado con Apache Iceberg            │
│  • Modelos dbt incrementales (is_incremental)                  │
│  • Cloud SQL en Alta Disponibilidad (HA Multi-AZ) + Replicas   │
│  • Enmascaramiento de PII en capa Silver (Hashing SHA-256)     │
│  • Observabilidad de datos automatizada (Elementary / Great E.)│
└───────────────────────────────┬────────────────────────────────┘
                                │
                                │ Requiere transacciones 24/7,
                                │ streaming continuo y compliance
                                ▼
┌────────────────────────────────────────────────────────────────┐
│   FASE 3: BANCO CORPORATIVO TIER-1 (>1M Usuarios / Enterprise) │
│   • Capacidad: Billones de transacciones (Petabytes)           │
│   • TCO: > $15,000 USD/mes | SLA 99.99%                        │
├────────────────────────────────────────────────────────────────┤
│  Distributed Lakehouse & Event-Driven Engine                   │
│  • CDC en tiempo real con Apache Kafka / Debezium / Pub/Sub    │
│  • Motor Analítico Distribuido: BigQuery / Dataproc Spark      │
│  • Gobernanza Centralizada: Google Cloud Dataplex + HSM Key    │
│  • Arquitectura Multi-Región Activo-Activo con DR estricto     │
│  • Gateway Corporativo de LLM con Red-Teaming y WAF            │
└────────────────────────────────────────────────────────────────┘
```

---

## 3. Matriz Comparativa 360°: FinTech vs. Banco Tier-1

| Dimensión Técnica | Fase 1: Actual (FinTech Ágil) | Fase 3: Enterprise (Banco Tier-1) | Diagnóstico & Brecha Real |
| :--- | :--- | :--- | :--- |
| **Motor de Cómputo ETL** | **DuckDB (Single-node)** en contenedor de 16 GB RAM | **Cómputo Distribuido** (BigQuery, Spark, Snowflake) | **Válido para <50M filas**. Excede memoria física si el dataset analítico supera 50 GB. |
| **Formato del Lakehouse** | **Parquet plano** particionado por Hive en GCS | **Open Table Format (Apache Iceberg / Delta Lake)** | **Brecha media**. Falta control de concurrencia ACID y mutaciones de registros (*updates/deletes*). |
| **Frecuencia de Ingesta** | **Batch diario** (~2.5 min de procesamiento) | **Streaming / CDC continuo** (Kafka, Pub/Sub, Flink) | **Brecha alta**. Un banco comercial requiere actualización de saldos y cargos en tiempo real (< 2 seg). |
| **Base de Datos Serving** | **Cloud SQL PostgreSQL (db-f1-micro)** con hibernación | **Cloud SQL HA Multi-AZ / Spanner / Aurora** con read replicas | **Brecha alta**. La micro-instancia colapsaría bajo concurrencia masiva (>50 transacciones por segundo). |
| **Seguridad del Agente** | **FastAPI tool layer determinista** fuera del prompt | **API Gateway mTLS, RBAC estricto, HSM y WAF** | **Excelente acierto**. Cumple las directrices OWASP LLM-01/02 al aislar la política del prompt. |
| **Gobernanza y PII** | Secret Manager para API keys; exclusión de fraude | **Tokenización PII (PCI-DSS), Dataplex y Vault HSM** | **Brecha media-alta**. Los datos personales (`document_number`) están en texto claro en GCS. |
| **Orquestación y SLA** | **Cloud Run Job** con reintento simple | **Cloud Composer (Airflow) / Temporal** con PagerDuty | **Brecha media**. Excelente para jobs atómicos, insuficiente para flujos complejos con SLA bancario. |

---

## 4. Modelo Granular de Costos (TCO) y Proyección por Fases

A continuación se detalla cómo escalan los costos operativos mensuales en relación directa con las tareas técnicas implementadas en cada fase de madurez:

### Tabla de Desglose de Costos Mensuales (USD)

| Componente de Infraestructura | Fase 1: Actual (MVP / FinTech) | Fase 2: Scale-Up Neobanco | Fase 3: Banco Tier-1 | Justificación Técnica del Costo |
| :--- | :---: | :---: | :---: | :--- |
| **Almacenamiento (GCS / Lakehouse)** | $0.03 | $15.00 | $350.00 | De 1.1 GB en Fase 1 a cientos de TB particionados con metadatos Iceberg y snapshots en Fase 3. |
| **Cómputo ETL / Transformación** | $1.20 | $60.00 | $2,800.00 | De Cloud Run Job (2.5 min/día) a Dataproc Serverless (Apache Spark) o slots dedicados de BigQuery. |
| **Base de Datos Serving (PostgreSQL)** | $7.50 | $180.00 | $4,200.00 | De `db-f1-micro` hibernable a clúster Multi-AZ con réplicas de lectura y Cloud Spanner global. |
| **Ingesta Continua y Streaming (CDC)** | $0.00 | $40.00 | $1,800.00 | De batch programado sin costo fijo a clústeres gestionados de Apache Kafka (Confluent/MSK) o Pub/Sub. |
| **Infraestructura de Agente & Backend** | $5.00 | $85.00 | $1,200.00 | Servicios Cloud Run autoescalables con balanceadores de carga Cloud Armor y WAF. |
| **Consumo de Tokens LLM (OpenRouter/IA)** | $20.00 | $350.00 | $4,500.00 | De ~10.000 disputas/mes con `gpt-4o-mini` a millones de interacciones con modelos híbridos y fine-tuning. |
| **Gobernanza, PII y Observabilidad** | $0.00 | $90.00 | $2,200.00 | Google Cloud Dataplex (catálogo y linaje), Google Cloud KMS (HSM para PCI-DSS) y DataDog. |
| **TOTAL ESTIMADO MENSUAL (TCO)** | **~$33.73 USD** | **~$820.00 USD** | **~$17,050.00 USD** | **Escala predictiva acorde al valor y volumen de negocio.** |

---

### Análisis de Economía Unitaria (*Unit Economics*)

| Métrica Unitaria | Fase 1: FinTech Actual | Fase 2: Scale-Up | Fase 3: Banco Tier-1 |
| :--- | :---: | :---: | :---: |
| **Usuarios Activos Mensuales (MAU)** | Hasta 100.000 | 100.000 a 1.000.000 | > 5.000.000 |
| **Volumen de Transacciones Procesadas** | ~23,5 Millones | ~250 Millones | > 2.500 Millones |
| **Costo por Usuario Activo (Costo/MAU)** | **$0.00033 USD** | **$0.00082 USD** | **$0.00341 USD** |
| **Costo por Millón de Transacciones** | **$1.43 USD** | **$3.28 USD** | **$6.82 USD** |
| **Costo por Resolución de Disputa (Chat)** | **~$0.0025 USD** | **~$0.0018 USD** | **~$0.0012 USD** |

> [!NOTE]
> En la Fase 3, aunque el costo total absoluto se eleva debido a los estrictos requerimientos de redundancia y auditoría regulatoria bancaria, el **costo por disputa resuelta disminuye** gracias a técnicas como *Prompt Caching*, modelos locales especializados y enrutamiento semántico ultra-eficiente con TypeSafe.

---

## 5. Aciertos Críticos de Grado Enterprise en el Diseño Actual

Aun habiendo sido desarrollada bajo condiciones de hackathon, la arquitectura adopta tres patrones fundamentales de ingeniería de software moderna:

1. **Separación Estricta de Almacenamiento y Cómputo:**
   - La base de datos relacional no actúa como "vertedero" de datos crudos. Solo almacena vistas materializadas limpias y optimizadas para servicio (`gold.*`).
   - Bronze y Silver se preservan en almacenamiento de objetos (GCS), desacoplando los costos de almacenamiento analítico de los costos de licencia/hardware de base de datos.
2. **Quality Gates con Shift-Left Testing (dbt build):**
   - Publicación condicionada al 100% de éxito en 121 pruebas automatizadas de dbt. Si una fuente externa introduce nulos en claves primarias o monedas inconsistentes, el pipeline se aborta y la base operativa no se contamina.
3. **Aislamiento Determinista del Agente (Defensa contra OWASP LLM-01/02):**
   - El modelo de lenguaje (LLM) **no tiene credenciales de conexión directa a PostgreSQL**.
   - Toda interacción ocurre mediante endpoints REST (`backend/`) que validan la sesión JWT y los límites monetarios en código imperativo, previniendo ataques de inyección de prompt o manipulación de balances.

---

## 6. Factores de Ruptura y Límites Duros (Failure Modes)

Si la configuración actual se enfrentara sin modificaciones a un tráfico bancario masivo:

* **OOM (*Out of Memory*) en DuckDB:** Al superar ~80M–100M filas o ante archivos masivos de eventos digitales, el proceso superará el límite de RAM del contenedor (16–32 GB) y Cloud Run Job terminará con error 137.
* **Saturación de Conexiones en Cloud SQL:** Una instancia `db-f1-micro` soporta un máximo de 25–50 conexiones simultáneas. Un pico de tráfico concurrente bloqueará el microservicio bancario con errores `FATAL: remaining connection slots are reserved`.
* **Ausencia de Transaccionalidad en el Bucket:** Si dos ejecuciones de ETL se solapan o un job falla a medio escribir, quedarán archivos Parquet huérfanos o lecturas inconsistentes sin un catálogo ACID (Iceberg).
* **Transferencia Inter-Cloud Ineficiente:** Leer desde AWS S3 hacia GCP Cloud Run Job genera costos de egress en AWS y latencia de red innecesaria. En producción, la ingesta debe consolidarse en la misma nube o mediante enlaces dedicados (*Cloud Interconnect*).

---

## 7. Análisis de Brechas Regulatorias y Cumplimiento (Compliance)

Para operar en mercados financieros regulados (CNBV en México, Superfinanciera en Colombia, CMF en Chile, o regulaciones globales PCI-DSS y GDPR):

1. **Protección de Datos Personales (PII):** Los números de documento y nombres de clientes residen actualmente en texto claro dentro de los archivos Parquet en GCS. Se requiere enmascaramiento con *tokenización* o hashing irreversible para analítica.
2. **Aislamiento de Señales de Fraude:** El dataset original contiene columnas de ground-truth (`is_fraud`, `fraud_score`). La arquitectura actual respeta la regla de negocio de **no exponer estas columnas como señal de entrada al LLM** en el tool layer, cumpliendo el principio ético y operativo bancario.
3. **Auditoría e Inmutabilidad:** Los logs de auditoría (`agent.trace_log` y `ops.etl_runs`) deben replicarse en almacenamiento inmutable (*WORM - Write Once, Read Many*) para soportar inspecciones de cumplimiento legal.

---

## 8. Hoja de Ruta de Migración y Tareas Técnicas

### Fase 1: Inmediata (MVP / FinTech Temprana) — *Estado Actual Reforzado*
- [x] Preservación de Bronze y Silver en GCS Parquet ZSTD con soporte local configurable.
- [ ] Incorporar un pool de conexiones liviano (`pgbouncer` o Cloud SQL Auth Proxy) en `backend/` para blindar la base de datos.
- [ ] Aplicar hashing unidireccional (SHA-256) sobre `document_number` y correos en la capa Silver para anonimización de PII.

### Fase 2: Scale-Up (Neobanco Mediano / 100k - 1M Usuarios)
- [ ] Migrar las tablas transaccionales en dbt a **modelos incrementales** (`is_incremental()`) para procesar solo deltas diarios.
- [ ] Configurar **Apache Iceberg** sobre GCS mediante `dbt-duckdb` o PySpark para garantizar transacciones ACID, viajes en el tiempo y compactación de archivos.
- [ ] Escalar Cloud SQL a instancia estándar con réplica de lectura para consultas analíticas y alta disponibilidad zonal.

### Fase 3: Banco Corporativo Tier-1 (>1M Usuarios / Enterprise)
- [ ] Implementar captura de datos en cambio (**CDC**) desde los sistemas core bancarios utilizando Apache Kafka / Debezium hacia Google Cloud Storage.
- [ ] Sustituir el motor de procesamiento por **BigQuery Serverless** o **Dataproc Serverless (Apache Spark)** para procesamiento distribuido masivo.
- [ ] Activar **Google Cloud Dataplex** para gestión automatizada de linaje, calidad de datos y políticas de enmascaramiento dinámico exigidas por auditores.

---

## 9. Argumentario Estratégico para Comités Técnicos e Inversionistas

Si debes defender esta arquitectura ante un Comité de Arquitectura Bancaria o un panel de Due Diligence técnico, la narrativa recomendada es:

> *"Nuestra arquitectura no es un prototipo improvisado; es una solución de **Fase 1 optimizada al límite en costo-beneficio**. Hemos implementado los mismos principios de desacoplamiento de almacenamiento (Lakehouse en Parquet), calidad estricta (121 tests de dbt) y aislamiento de permisos de seguridad (OWASP LLM) que exige un gran banco, pero ejecutándolos con herramientas serverless ligeras (DuckDB y Cloud Run) para operar con un TCO menor a $40 USD al mes. Gracias a que el microservicio de banca y el agente operan a través de contratos de API REST deterministas, podemos evolucionar el backend de datos de DuckDB a Apache Iceberg y BigQuery en Fase 2 y 3 **sin tener que reescribir una sola línea del agente conversacional ni de la lógica de negocio**."*
