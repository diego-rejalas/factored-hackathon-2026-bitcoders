# Revisión del PR #1 (backend, agente, chat y GCP): hallazgos para mejorar

El PR se fusionó en `main` como base (commit `8c338ee`). Esta es la lista de lo que hay que corregir o decidir. Método: lectura del diff completo, pruebas propias del PR (22 del backend y 33 del agente, todas pasan) y tres escenarios adicionales ejecutados contra el grafo del agente con sus utilidades de prueba en memoria. No se desplegó nada para esta revisión.

Alcance acordado: el `frontend/` y el `backend/` del PR se mantienen tal cual (son para la prueba de su autor); lo que sigue sobre ellos es información para decidir, no cambios hechos.

## 1. Fallos de lógica del agente (reproducidos y **corregidos** el 2026-10-02)

Los tres escenarios de la tabla ya se comportan como "qué debería pasar" y tienen pruebas de regresión en `agent/tests/`. Cambios: el agente ahora busca transacciones en todos los estados; una transacción `Approved` o `Pending` que el cliente no reconoce escala siempre (`posted_charge_disputed`); un monto sin conversión a USD escala (`amount_unknown`) en lugar de contar como cero; y un reclamo que no identifica la transacción (ni comercio ni monto) no se cierra: el agente propone la candidata y pide confirmación, y solo un "sí" sin negaciones la confirma.

| # | Escenario | Qué pasa | Qué debería pasar |
|---|---|---|---|
| 1 | Cliente con una sola transacción rechazada (Farmacia, 120 USD) y un cobro **aprobado** de 980 USD que no reconoce, dice "me hicieron un cobro que no reconozco" | Se auto-resuelve sobre la farmacia y responde "el dinero nunca salió de tu cuenta" | Preguntar cuál es; el reclamo vago no puede cerrarse contra una transacción que el cliente no describió |
| 2 | Rechazada de 9,5 millones de COP sin conversión a USD (`amount_usd_effective` nulo) | `effective_usd` convierte el nulo en 0, pasa el umbral y se auto-resuelve | Monto desconocido debe escalar |
| 3 | "No reconozco el cobro de 980 en Casino Royal" (transacción **aprobada**, con comercio y monto) | Solo se buscan `Declined` y `Reversed`; responde "no encontré una transacción rechazada" y pide aclaración | Una aprobada desconocida es el caso de fraude y debe escalar siempre |

Otros puntos del agente:
- Un caso auto-resuelto queda con estado `open` en la base y nada lo cierra (una prueba lo afirma).
- El texto del LLM reemplaza la respuesta determinista sin validarla, incluso en escalamientos sin hechos que citar. Falta un validador de salida (id de caso, estado y montos coinciden; frases como "reembolsaremos" prohibidas).
- No hay defensa determinista contra manipulación ("ignora las reglas…").
- El idioma se detecta con una lista corta de palabras; todo lo que no esté en ella cae como español.
- La "integración con TypeSafe" llama a una API inventada (`TYPESAFE_API_URL`, otro formato). El SDK real es `typesafe-sdk` con `client.system_one(...)`. Ver `spec/AGENT_FLOW_JEV.md`.
- `GUARDRAIL_MAX_USD` por defecto es 500; la propuesta de `spec/DISPUTE_WORKFLOW.md` es 5.000 (percentil 90 de los montos). Decisión de producto pendiente.
- Un `Pending` casi nunca se liquida en estos datos (88.035 de 88.343 son anteriores a 3 días): decidir qué hace el agente con ellos.

## 2. Seguridad e infraestructura (revisado en el código)

- **Cloud SQL con IP pública y `0.0.0.0/0` autorizado**, solo con contraseña.
- **Backend y agente se conectan con el usuario `app`**, propietario de la base. El backend crea tablas al arrancar (`CREATE TABLE IF NOT EXISTS`) y el agente escribe sus trazas directo en Postgres, lo que contradice "el agente nunca toca la base". Falta separar un rol de solo lectura para `gold` y otro acotado a `app.*` y `agent.trace_log`.
- **Servicios abiertos a todos (`allUsers`)**: backend, agente y frontend. El backend debería ser interno.
- `grant_access.sh` entrega `roles/editor` del proyecto a cada compañero y guarda contraseñas en un archivo local (ignorado por git).
- CI con una llave JSON de cuenta de servicio con rol Editor; mejor Workload Identity Federation.
- `POST /session` valida `customer_id` + número de documento sin límite de intentos; un documento sirve de contraseña.
- `deletion_protection = false` en varios recursos; sin presupuesto ni alertas; sin monitoreo.
- Dependencias sin fijar (`>=`).
- Región `us-central1` mientras el bucket del organizador está en AWS `us-east-2`: la carga cruza de nube (el propio Terraform comenta ~40 min). `us-east4` es la región de GCP más cercana.

## 3. Cambios de arquitectura que trae el PR y chocan con decisiones previas

| Decisión previa | El PR |
|---|---|
| Airflow orquesta | **Sin Airflow**: `infra/gcp/etl/run_pipeline.py` en un Cloud Run Job |
| dbt sobre Postgres (`dbt-postgres`), servicio propio | `dbt-duckdb` embebido, en RAM |
| bronze, silver y gold visibles en Postgres | Solo `gold` se publica; bronze y silver quedan como Parquet en GCS |
| Agente con PydanticAI | LangGraph |
| Frontend en Vercel con adaptador de chat | Chat propio, pensado para Cloud Run |
| Railway como IaC | `railway.ts` marcado legacy; Terraform de GCP como primario |

Estado tras la fusión: conviven los dos pipelines. El perfil de dbt por defecto (`prod`) apunta a DuckDB; el servicio dbt de Railway ahora pasa `--target postgres` (`infra/dbt/app.py`). El Railway `backend` redespliega con el código nuevo (rutas `backend/**`), que exige `PG_*` y `SESSION_JWT_SECRET`: ese despliegue fallará su healthcheck y Railway debería conservar la versión anterior; hay que configurar las variables o dejar de redesplegarlo.

## 4. Lo reutilizable (bueno)

- Backend: JWT con vencimiento, consultas parametrizadas, titularidad en el `WHERE` de cada consulta, `amount_usd_effective`, disputas con eventos.
- Agente: guardrail como tablas en código, fraude en español y portugués, `verify` que relee el caso, trazas por paso.
- Pruebas propias (55) y CI que construye las imágenes.
- Sin credenciales en el diff (patrones de claves, contraseñas y URLs con usuario revisados).

## 5. Pendiente de decidir por el equipo

1. Nube de destino (GCP con los créditos de US$300, o AWS) y qué parte del Terraform se reutiliza.
2. Dónde corre Airflow y si bronze y silver vuelven a Postgres.
3. LangGraph o PydanticAI para el agente.
4. Umbral de monto y manejo de `Pending`.
