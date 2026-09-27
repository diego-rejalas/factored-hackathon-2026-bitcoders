# Arquitectura por verticales

Versión reducida del pizarrón original (ver `arquitecture-bp.png`), recortada para 8 días con 3 personas y deploy en Railway + Vercel. Se organiza en 4 verticales para trabajar en paralelo. Workflow-agnóstica — no depende de cuál de las 4 opciones (A/B/C/D) gane el voto del equipo.

Se cae del pizarrón original: k8s/VMs, Kubeflow, Kafka, Temporal, streaming, blob storage. Razón: el reto no exige streaming ni multi-agente ni entrenar modelo propio, y cada una de esas piezas es días de setup que no hay.

## Big picture

```mermaid
flowchart LR
    subgraph client["Cliente"]
        FE[Frontend chat<br/>Vercel]
    end

    subgraph agentv["agent/ — Agente + Guardrail"]
        AGENT[Agent Orchestrator<br/>FastAPI + LangGraph]
        GUARD[Guardrail determinista<br/>tabla intent→permiso]
        AGENT --> GUARD
        GUARD --> AGENT
    end

    subgraph bankv["backend/ — Microservicio de banca"]
        BANK[Banking Mock API<br/>FastAPI]
    end

    subgraph etlv["infra/airflow/ + data/ — Ingesta + ETL"]
        INGEST[DAG: ingesta<br/>data/dags/]
        DBT[dbt<br/>data/dbt/]
        INGEST --> DBT
    end

    subgraph data["Postgres"]
        RAW[(raw.*)]
        CLEAN[(clean.*)]
        TRACE[(trace_log)]
    end

    S3[(S3<br/>LATAM Bank dataset)] --> INGEST
    DBT --> RAW
    DBT --> CLEAN

    FE -->|POST /chat| AGENT
    AGENT -->|logs cada paso| TRACE
    AGENT -->|HTTP tools| BANK
    BANK -->|SQL| CLEAN
    AGENT -.->|LLM calls| OR[OpenRouter]
```

## Diagrama de despliegue

```mermaid
flowchart TB
    subgraph vercel["Vercel"]
        FE[Frontend chat]
    end

    subgraph railway["Railway project: factored-hackathon (.railway/railway.ts)"]
        AGENT[agent/<br/>servicio]
        BANK[backend/<br/>servicio]
        AIRFLOW[infra/airflow/<br/>servicio, DAGs+dbt horneados]
        PG[(Postgres<br/>addon)]
    end

    subgraph external["Externo"]
        OR[OpenRouter API]
        S3[S3 bucket<br/>read-only]
    end

    USER((Usuario)) --> FE
    FE -->|HTTPS| AGENT
    AGENT -->|HTTP interno| BANK
    AGENT -->|HTTPS| OR
    BANK -->|SQL| PG
    AGENT -->|trace_log| PG

    AIRFLOW -.->|DAG: extrae + carga| PG
    AIRFLOW -.->|lee| S3
```

## 1. Ingesta

**Responsabilidad:** bajar los CSVs particionados de S3 (bucket read-only del data dictionary) y volcarlos crudos a Postgres, sin transformar.

- Orquestado por **Airflow standalone** (1 solo contenedor — servicio `railwayapp-airflow`, deployment config en `infra/airflow/`), no Airbyte. Airbyte quedó descartado: su modelo de despliegue por Docker Compose está descontinuado por el propio proyecto (el único camino soportado ahora es `abctl` sobre un clúster Kubernetes, que no encaja en Railway como "otro servicio más"). Ver intento fallido documentado más abajo.
- Un DAG simple en `data/dags/`: task de extracción (boto3, S3 → `raw.*`) → task de trigger de dbt (`dbt run` + `dbt test`, proyecto en `data/dbt/`).
- **`infra/` vs `data/` — separación deliberada:** `infra/airflow/` es solo config de despliegue (Dockerfile, entrypoint, healthcheck); `data/dags/` y `data/dbt/` son el contenido real del pipeline (lógica de negocio de datos). El mercado a escala separa esto más todavía — DAGs sincronizados por un sidecar git-sync a un volumen compartido, e imagen de dbt desplegada y versionada aparte del cluster de Airflow, disparada por un operator — para no tener que rebuildear/redeployar todo Airflow cada vez que cambia un DAG o un modelo dbt. A nuestra escala (pocos DAGs, 8 días, 1 contenedor standalone) eso es sobre-ingeniería: `infra/airflow/Dockerfile` hornea `data/dags/` y `data/dbt/` directo en la imagen en build time — cada cambio dispara un rebuild, aceptable acá. Documentado como camino de escalamiento, no implementado ahora.
- Destino: schema `raw.*` en Postgres (Railway), una tabla por tabla del dataset, columnas como texto — espejo fiel de lo que llegó (evidencia de lineage/auditoría).
- **Contrato de salida:** `raw.<tabla>` existe y tiene el mismo número de filas que S3 (contar y loggear al final de la carga).

### Por qué Airflow y no un script suelto

Con datos 100% estáticos, un orquestador no es necesario para que el pipeline *funcione* — pero si el equipo quiere mostrar re-ejecución programada, reintentos visibles y una UI de runs para el video pitch, Airflow standalone (single-container, sin Celery/Redis/K8s) da eso sin el costo de infraestructura de la topología completa. Es una elección de **presentación/observabilidad**, no de necesidad técnica: el reto es explícito en que con solo datos estáticos alcanza con "demonstrate update correctness with a clearly labeled test fixture", sin exigir streaming ni orquestación pesada.

### Escalabilidad (cómo se responde sin tener que correrlo)

El reto pide diseñar pensando en escalabilidad, no necesariamente demostrarla corriendo a escala en 8 días. Postura: pipeline por lotes, idempotente (cada carga puede re-correrse sin duplicar filas — `ON CONFLICT DO NOTHING`/`MERGE` en la task de carga), apuntando a un Postgres que se puede migrar a una instancia más grande sin cambiar código. Si los datos llegaran en streaming o creciera 10x el volumen, el punto de extensión es agregar un consumidor de eventos (Kafka/Kinesis) antes de la task de extracción y correr Airflow con CeleryExecutor multi-worker — documentado como camino de escalamiento, no implementado ahora.

### Intento fallido con Airbyte (documentado para la entrega — "report limitations")

Se intentó self-hostear Airbyte OSS 2.1.1 en Railway (server + worker, sin webapp — la imagen `airbyte/webapp:2.1.1` no existe, Airbyte discontinuó esa línea de versiones para self-host en contenedores sueltos). Requirió Temporal + Elasticsearch + Postgres dedicado además del server/worker, y depuración empírica de variables no documentadas (`WORKSPACE_ROOT`, `DATABASE_USER`, `AIRBYTE_URL`) vía logs de crash. Se abandonó al confirmar que Airbyte eliminó el soporte de Docker Compose y el único camino oficial (`abctl`) requiere un clúster Kubernetes completo. Fork con los fixes queda documentado en `diego-rejalas/railwayapp-airbyte-private` (privado) por si se retoma.

## 2. ETL / limpieza

**Responsabilidad:** transformar `raw.*` en `clean.*`, resolviendo lo que encontramos en `DATA_FINDINGS.md` (nulls, moneda MXN faltante, tipos, dedupe donde aplique). Vive en `data/dbt/`.

- dbt sobre el mismo Postgres. Modelos `stg_*` (cast de tipos, nulls tratados) → modelos `clean_*` (joins resueltos, listos para que el tool layer los lea).
- Tests de dbt (`schema.yml`): `not_null`, `unique`, `accepted_values` sobre los campos clave (esto cubre "contratos de datos" y "quality checks" que pide el reto).
- Great Expectations no entra — dbt tests + pandera puntual si hace falta algo que dbt no cubre bien, sin levantar un servicio nuevo.
- **Contrato de salida:** `clean.<tabla>` versionado por los modelos dbt, con `dbt test` pasando en CI/manual antes de que el tool layer dependa de ellos.

## 3. Microservicio de banca (mock banking API) — `backend/`

**Responsabilidad:** es el "service/tool layer" que el reto exige explícitamente para enforced de permisos — "Enforce access to each customer's records and action permissions in the service or tool layer", no en el prompt del LLM.

- Un servicio FastAPI separado (Railway), con endpoints REST deterministas: `GET /customers/{id}`, `GET /customers/{id}/transactions`, `POST /cases`, `POST /cards/{id}/block`, etc. — según el workflow que gane el voto.
- Cada endpoint valida sesión/permiso **antes** de tocar `clean.*` — esto es lo único que de verdad se beneficia de ser un servicio aparte (aísla el enforcement de permisos del código del agente, para que quede claro en la demo/video que la política no vive en el prompt).
- Lee de `clean.*` en Postgres.
- **Por qué sí separarlo (y no meterlo en el mismo proceso del agente):** es la pieza que el reto pide mostrar explícitamente como "fuera del modelo" — tenerla como servicio HTTP propio, con sus propios logs, hace la separación obvia y fácil de explicar en el video pitch. Es el único microservicio real que vale la pena con el tiempo que hay; todo lo demás se queda en un solo proceso.
- **Contrato:** OpenAPI expuesto por FastAPI (gratis con FastAPI), documentado como "mock banking tool" con sus límites (qué simula, qué no) — cumple el requisito de documentar contratos de sandbox services.

## 4. Agente + guardrail — `agent/`

**Responsabilidad:** el orquestador conversacional. Habla con el usuario, decide, llama al microservicio de banca, verifica, escala.

- Servicio FastAPI separado (Railway) con LangGraph adentro. Grafo con nodos explícitos: `understand → decide → act → verify → escalate`.
- Las "tools" del agente son clientes HTTP delgados al microservicio de banca (vertical 3) — el LLM nunca toca Postgres directo.
- **Guardrail determinista:** vive en el nodo `decide`, ANTES de `act`. Es una tabla/config (no un prompt) que dice qué tool puede invocarse según intent detectado + estado de sesión/autenticación. Si falta permiso o falta info → fuerza camino de aclaración o abstención, no deja que el LLM decida solo.
- Verificación: después de que `act` llama al microservicio de banca, `verify` vuelve a consultar el estado (no confía en que el LLM "diga" que funcionó).
- LLM vía OpenRouter (flexibilidad de modelo/fallback).
- Logging estructurado de cada paso del grafo a `trace_log` en Postgres — evidencia de auditoría para el handoff a humano y para el reporte de evaluación.
- **Contrato:** expone `POST /chat` al frontend; nunca expone acceso directo a la base de datos ni al microservicio de banca desde el cliente.

## Mapa de servicios a desplegar (mínimo viable)

| Servicio | Carpeta | Plataforma | Contiene |
|---|---|---|---|
| Postgres | — (addon) | Railway | `raw.*`, `clean.*`, `trace_log` |
| railwayapp-airflow | `infra/airflow/` (+ `data/dags/`, `data/dbt/` horneados) | Railway | Vertical 1+2 |
| backend | `backend/` | Railway | Vertical 3 |
| agent | `agent/` | Railway | Vertical 4 (LangGraph + guardrail) |
| frontend | `frontend/` | Vercel | UI de chat |

Total: 3 servicios de aplicación en Railway + 1 Postgres + 1 frontend en Vercel. Nada de k8s, Kafka, Temporal, Kubeflow.

## Configuración de Railway como código

Lección de la sesión: configurar servicios a mano (dashboard o vía MCP) es rápido pero no queda versionado ni es reproducible por otra persona del equipo — así se armó y desarmó Airbyte sin dejar rastro reproducible.

Railway deprecó `railway.toml`/`railway.json` (Config as Code, corte duro 2026-12-01) a favor de **Infrastructure as Code**: un único archivo `.railway/railway.ts` en la raíz del repo, gestionado con la Railway CLI (`railway config plan` / `railway config apply`). Convención del proyecto:

- **Un solo archivo `.railway/railway.ts`** declara todos los servicios, volúmenes y la base de datos del proyecto — build, healthcheck, restart policy, montajes de volumen, y qué variables se preservan (`preserve()` para secretos que ya viven en Railway, nunca en el repo).
- Cada servicio (`infra/airflow/`, `backend/`, `agent/`) sigue teniendo su propio `Dockerfile` y `.env.example` en su carpeta (documentación de qué variables necesita), pero el *despliegue* (qué servicio existe, con qué config) se define en el `.railway/railway.ts` único, no en un `railway.toml` por carpeta.
- Flujo: `railway config plan` (previsualiza, nunca escribe nada) → revisar → `railway config apply` (confirma antes de aplicar; cambios destructivos requieren confirmación explícita).
- El repo `railwayapp-airbyte-private` con los fixes de Airbyte queda como referencia local (por si se retoma), no como servicio activo en Railway ni en el IaC.

## Próximo paso

Falta definir, una vez el equipo vote el workflow: los endpoints exactos del microservicio de banca, los intents/tools del agente, y las reglas concretas del guardrail (qué se auto-resuelve, qué escala) — eso ya es específico de la Opción A/B/C/D elegida, no de esta arquitectura base.
