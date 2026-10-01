# Propuesta para servir modelos de ML sobre el stack GCP

> 2026-10-01 · `docs(ml): add ML serving proposal — train job, batch scores and in-process intent model` · repo `factored-hackathon-2026-bitcoders`

## Por qué

El reto exige evaluar al menos un componente aprendido contra un baseline
(criterio 4 de `doc/Factored AI & Data Hackathon 2026.md`), y la app todavía no
tiene un camino definido para entrenar, versionar y servir modelos. Hacía falta
decidir cómo hacerlo sin sumar infraestructura nueva: el stack ya tiene Cloud
Run Jobs, el lakehouse en GCS con Parquet y Cloud SQL con `gold.*` y `ops.*`.

## Qué cambió

Se agrega `spec/ML sobre el stack GCP.html`, una página autocontenida con la
propuesta. Es la versión descargada del artifact que se revisó en la sesión.
Contiene:

- **Diagrama offline**: los 6 pasos reales de `infra/gcp/etl/run_pipeline.py` y
  los 7 pasos de un job `train` nuevo, con lo que cada paso lee o escribe en GCS
  (`bronze/`, `silver/`, `models/<modelo>/<versión>/`) y en Cloud SQL
  (`gold.*`, `gold.transaction_risk_scores`, `ops.etl_runs`,
  `ops.model_registry`).
- **Diagrama de secuencia online**: un mensaje de chat recorrido nodo por nodo
  del grafo de LangGraph (`understand`, `decide`, `act`, `verify`, `escalate`,
  `respond`), con las llamadas entre `main.py`, `intents.py`, el modelo en
  memoria, `tools.py`, `guardrail.py`, el backend, OpenRouter, Cloud SQL y GCS.
- **Tabla de conexiones**: las 15 interfaces entre componentes, con protocolo,
  datos y el archivo donde vive cada una hoy.
- **Criterio de serving**: scores que no dependen del mensaje van por lotes a
  una tabla gold que expone el backend; modelos que dependen del mensaje (por
  ejemplo, intents) se cargan en memoria en el agente desde GCS con
  `MODEL_VERSION` fija. La regla de umbral del score va en
  `agent/app/guardrail.py`, junto a la de USD 500.
- Reglas de datos (`is_fraud` solo como label, `fraud_score` nunca como
  feature, `run_id` del ETL en el manifiesto, `model_version` en
  `agent.trace_log`) y qué se descarta (Vertex AI Endpoints, MLflow, un
  servicio `ml-serving` propio salvo dependencias pesadas).

## Impacto

Solo documentación: no cambia código, infraestructura ni datos. Los
componentes marcados con ★ en la página (job `train`, tablas nuevas, modelo en
memoria) son propuesta y no existen todavía.

## Verificación

- Las conexiones y nombres de la página se contrastaron con el código:
  `agent/app/graph.py`, `intents.py`, `guardrail.py`, `tools.py`, `tracing.py`,
  `backend/app/db.py`, rutas del backend, `frontend/components/Chat.tsx`,
  `infra/gcp/main.tf` y `run_pipeline.py`.
- Los diagramas se generaron con posiciones calculadas y un chequeo que frena si
  una etiqueta no entra en su flecha; se revisó una captura en Chrome headless
  sin cruces ni solapamientos.
- Sin verificar: que `backend` y `agent` corran con 512 MiB (default de Cloud
  Run, se infiere de que `main.tf` no declara `resources`), y el costo actual de
  Vertex AI Endpoints.
